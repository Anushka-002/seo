import numpy as np

from app.rag.chunking import chunk_page, chunk_text, estimate_tokens
from app.rag.embeddings import HashingEmbedder, get_embedder
from app.services.scraper import extract_page

LONG = " ".join(
    f"Sentence number {i} talks about running shoes and cushioning." for i in range(120)
)


def test_chunks_respect_size_and_overlap():
    chunks = chunk_text(LONG, source_url="u", rank=1, chunk_tokens=300, overlap_tokens=50)
    assert len(chunks) > 1
    assert all(estimate_tokens(c.text) <= 300 + 10 for c in chunks)
    # overlap: end of chunk i shares words with start of chunk i+1
    tail = set(chunks[0].text.split()[-20:])
    head = set(chunks[1].text.split()[:40])
    assert tail & head
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert len({c.id for c in chunks}) == len(chunks)


def test_tiny_fragments_dropped_but_single_short_text_kept():
    assert chunk_text("Too short.", source_url="u")[0].text == "Too short."
    assert chunk_text("", source_url="u") == []


def test_chunk_page_carries_headings(pages_html):
    page = extract_page(pages_html["runnerlab.test"], "https://runnerlab.test/", 1)
    chunks = chunk_page(page)
    headings = {c.heading for c in chunks}
    assert "How to choose cushioning" in headings
    assert all(c.source_url == page.url and c.rank == 1 for c in chunks)
    cushion = next(c for c in chunks if c.heading == "How to choose cushioning")
    assert cushion.embed_text.startswith("How to choose cushioning.")


def test_hashing_embedder_is_normalised_and_deterministic():
    e = HashingEmbedder()
    a = e.embed(["running shoes cushioning", "running shoes cushioning"])
    assert a.shape == (2, e.dim)
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0, atol=1e-5)
    assert np.array_equal(a[0], a[1])
    assert np.array_equal(e.embed(["running shoes cushioning"])[0], a[0])


def test_hashing_embedder_similarity_ordering():
    e = HashingEmbedder()
    q, near, far = e.embed(
        ["running shoe cushioning foam", "soft cushioning foam in running shoes", "tax law filing"]
    )
    assert q @ near > q @ far


def test_empty_text_gives_zero_vector_not_nan():
    v = HashingEmbedder().embed([""])
    assert not np.isnan(v).any()


def test_get_embedder_selects_backend_and_rejects_unknown():
    assert get_embedder("hashing").name == "hashing"
    import pytest

    with pytest.raises(ValueError):
        get_embedder("nope")
