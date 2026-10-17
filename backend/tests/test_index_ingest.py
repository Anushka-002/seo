import httpx
import numpy as np
import pytest

from app.rag.chunking import chunk_page
from app.rag.embeddings import HashingEmbedder
from app.rag.index import RagIndex
from app.services.ingest import build_competitor_index
from app.services.scraper import extract_page


@pytest.fixture
def index(pages_html):
    pages = [
        extract_page(h, f"https://{d}/", i)
        for i, (d, h) in enumerate(pages_html.items(), 1)
        if d != "thinpage.test"
    ]
    idx = RagIndex(HashingEmbedder())
    for p in pages:
        idx.add(chunk_page(p))
    yield idx
    idx.close()


def test_query_returns_most_relevant_section_first(index):
    top = index.query("how long do running shoes last before replacing", k=3)
    assert top[0].chunk.heading == "How long running shoes last"
    assert top[0].score >= top[-1].score
    assert all(-1.0 <= h.score <= 1.001 for h in top)


def test_matrix_aligned_with_chunks(index):
    assert index.matrix.shape == (index.size, index.embedder.dim)
    assert len(index.chunks) == index.size > 20
    assert np.allclose(np.linalg.norm(index.matrix, axis=1), 1.0, atol=1e-4)


def test_k_larger_than_index_and_empty_index():
    idx = RagIndex(HashingEmbedder())
    assert idx.query("anything") == []
    idx.close()


def test_indexes_are_isolated_from_each_other(pages_html):
    page = extract_page(pages_html["runnerlab.test"], "https://runnerlab.test/", 1)
    a, b = RagIndex(HashingEmbedder()), RagIndex(HashingEmbedder())
    a.add(chunk_page(page))
    assert b.size == 0 and b.query("cushioning") == []
    a.close()
    b.close()


async def test_end_to_end_ingest_with_cache(pages_html, settings, db):
    hits = {"serper": 0, "pages": 0}
    organic = [{"title": d, "link": f"https://{d}/post", "snippet": ""} for d in pages_html]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "google.serper.dev":
            hits["serper"] += 1
            return httpx.Response(200, json={"organic": organic})
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        hits["pages"] += 1
        return httpx.Response(
            200, text=pages_html[request.url.host], headers={"content-type": "text/html"}
        )

    embedder = HashingEmbedder()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        r1 = await build_competitor_index(
            "best running shoes", "us", settings=settings, db=db, embedder=embedder, client=client
        )
        first_pages = hits["pages"]
        r2 = await build_competitor_index(
            "best running shoes", "us", settings=settings, db=db, embedder=embedder, client=client
        )
    assert len(r1.pages) == 5 and r1.index.size > 20
    assert hits["serper"] == 1  # SERP cached
    assert hits["pages"] == first_pages  # scrape cached on second run (no new page fetches)
    assert r2.index.size == r1.index.size
    assert r2.index.query("carbon plate racing", 1)[0].chunk.heading == "Carbon plated racing shoes"
    r1.index.close()
    r2.index.close()
