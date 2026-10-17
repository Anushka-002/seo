"""Compose SERP -> scrape -> chunk -> embed -> index into one reusable step."""

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.rag.chunking import chunk_page
from app.rag.embeddings import Embedder, get_embedder
from app.rag.index import RagIndex
from app.services.cache import get_cached, set_cached
from app.services.scraper import ScrapedPage, scrape_pages
from app.services.serp import SerpData, fetch_serp

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Everything later phases need to analyse a draft."""

    serp: SerpData
    pages: list[ScrapedPage]
    index: RagIndex


def build_index(pages: list[ScrapedPage], embedder: Embedder) -> RagIndex:
    """Chunk and embed pages into a fresh in-memory index."""
    index = RagIndex(embedder)
    for page in pages:
        index.add(chunk_page(page))
    return index


async def build_competitor_index(
    keyword: str,
    country: str = "us",
    *,
    settings: Settings | None = None,
    db: Session | None = None,
    embedder: Embedder | None = None,
    client: httpx.AsyncClient | None = None,
) -> IngestResult:
    """Fetch top results, scrape them (cached per day), and build the RAG index."""
    settings = settings or get_settings()
    embedder = embedder or get_embedder()
    serp = await fetch_serp(keyword, country, settings=settings, client=client, db=db)

    cached = get_cached(db, "scrape", keyword, country)
    if cached:
        pages = [ScrapedPage(**p) for p in cached["pages"]]
        log.info("scrape cache hit")
    else:
        pages = await scrape_pages(serp.results, settings=settings, client=client)
        set_cached(db, "scrape", keyword, country, {"pages": [p.model_dump() for p in pages]})

    index = build_index(pages, embedder)
    log.info("index built", extra={"extra_fields": {"pages": len(pages), "chunks": index.size}})
    return IngestResult(serp=serp, pages=pages, index=index)
