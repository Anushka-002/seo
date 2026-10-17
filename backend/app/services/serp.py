"""Fetch top Google results: Serper.dev when a key is set, DuckDuckGo otherwise."""

import asyncio
import logging
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.services.cache import get_cached, set_cached

log = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/search"
# Domains whose pages are not useful long-form text competitors.
BLOCKED_DOMAINS = {
    "youtube.com", "youtu.be", "pinterest.com", "facebook.com", "instagram.com",
    "tiktok.com", "x.com", "twitter.com", "linkedin.com", "reddit.com", "quora.com",
}  # fmt: skip
BLOCKED_EXTENSIONS = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".zip")


class SerpError(RuntimeError):
    """Raised when search results cannot be fetched."""


class SerpResult(BaseModel):
    """One organic search result."""

    rank: int
    title: str
    url: str
    snippet: str = ""


class SerpData(BaseModel):
    """Search results plus related queries for a keyword."""

    keyword: str
    country: str
    results: list[SerpResult]
    related_searches: list[str] = []
    people_also_ask: list[str] = []


def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def is_scrapable(url: str) -> bool:
    """True for http(s) HTML-looking URLs outside the blocklist."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.path.lower().endswith(BLOCKED_EXTENSIONS):
        return False
    host = _domain(url)
    return not any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)


def _finalize(keyword: str, country: str, raw: list[dict], limit: int) -> list[SerpResult]:
    """Filter, dedupe URLs and renumber ranks 1..n."""
    out: list[SerpResult] = []
    seen: set[str] = set()
    for item in raw:
        url = (item.get("link") or item.get("href") or "").strip()
        if not url or url in seen or not is_scrapable(url):
            continue
        seen.add(url)
        out.append(
            SerpResult(
                rank=len(out) + 1,
                title=(item.get("title") or "").strip(),
                url=url,
                snippet=(item.get("snippet") or item.get("body") or "").strip(),
            )
        )
        if len(out) == limit:
            break
    return out


async def _serper(
    keyword: str, country: str, settings: Settings, client: httpx.AsyncClient
) -> SerpData:
    try:
        resp = await client.post(
            SERPER_URL,
            headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
            json={"q": keyword, "gl": country.lower(), "num": 20},
            timeout=settings.serp_timeout,
        )
    except httpx.HTTPError as exc:
        raise SerpError(f"Search request failed: {type(exc).__name__}") from exc
    if resp.status_code in (401, 403):
        raise SerpError(
            "The search provider rejected the API key. The site owner needs to check it."
        )
    if resp.status_code == 429:
        raise SerpError("Serper rate limit/quota reached. Try again later.")
    if resp.status_code != 200:
        raise SerpError(f"Serper returned HTTP {resp.status_code}.")
    data = resp.json()
    return SerpData(
        keyword=keyword,
        country=country,
        results=_finalize(keyword, country, data.get("organic", []), settings.serp_results),
        related_searches=[r["query"] for r in data.get("relatedSearches", []) if r.get("query")],
        people_also_ask=[r["question"] for r in data.get("peopleAlsoAsk", []) if r.get("question")],
    )


def _ddg_sync(keyword: str, country: str) -> list[dict]:
    try:
        from ddgs import DDGS  # newer package name
    except ImportError:
        from duckduckgo_search import DDGS
    return list(DDGS().text(keyword, region=f"{country.lower()}-en", max_results=20))


async def _duckduckgo(keyword: str, country: str, settings: Settings) -> SerpData:
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(_ddg_sync, keyword, country), timeout=settings.serp_timeout + 5
        )
    except Exception as exc:  # library raises various error types
        log.warning("duckduckgo search failed: %s", type(exc).__name__)
        raise SerpError(
            "Search results are temporarily unavailable. Please try again shortly."
        ) from exc
    return SerpData(
        keyword=keyword,
        country=country,
        results=_finalize(keyword, country, raw, settings.serp_results),
    )


async def fetch_serp(
    keyword: str,
    country: str = "us",
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    db: Session | None = None,
) -> SerpData:
    """Fetch (or load from today's cache) the top organic results for a keyword."""
    settings = settings or get_settings()
    cached = get_cached(db, "serp", keyword, country)
    if cached:
        log.info("serp cache hit")
        return SerpData(**cached)

    if settings.use_serper:
        owns = client is None
        client = client or httpx.AsyncClient()
        try:
            data = await _serper(keyword, country, settings, client)
        finally:
            if owns:
                await client.aclose()
    else:
        data = await _duckduckgo(keyword, country, settings)

    if not data.results:
        raise SerpError("No usable search results were returned for this keyword.")
    set_cached(db, "serp", keyword, country, data.model_dump())
    return data
