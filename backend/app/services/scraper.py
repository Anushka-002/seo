"""Polite async scraping + main-content extraction with heading structure."""

import asyncio
import logging
import re
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.services.netguard import guarded_client
from app.services.serp import SerpResult

log = logging.getLogger(__name__)
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")


class ScrapeError(RuntimeError):
    """Raised when too few pages could be scraped to build a useful index."""


class Heading(BaseModel):
    """A page heading (levels 1-3)."""

    level: int
    text: str


class Section(BaseModel):
    """Body text under one heading (heading '' = intro before the first heading)."""

    heading: str
    level: int
    text: str


class ScrapedPage(BaseModel):
    """Clean text and structure extracted from one page."""

    url: str
    rank: int
    title: str
    headings: list[Heading]
    sections: list[Section]
    word_count: int

    @property
    def text(self) -> str:
        """Plain text of the whole page (headings + body)."""
        parts = []
        for s in self.sections:
            if s.heading:
                parts.append(s.heading)
            parts.append(s.text)
        return "\n\n".join(p for p in parts if p)


def parse_markdown_sections(markdown: str) -> tuple[list[Heading], list[Section]]:
    """Split trafilatura markdown into headings and per-heading body sections."""
    headings: list[Heading] = []
    sections: list[Section] = []
    cur_heading, cur_level, buf = "", 0, []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append(Section(heading=cur_heading, level=cur_level, text=body))

    for line in markdown.splitlines():
        m = _HEADING.match(line.strip())
        if m:
            flush()
            buf.clear()
            cur_level, cur_heading = len(m.group(1)), m.group(2).strip()
            headings.append(Heading(level=cur_level, text=cur_heading))
        else:
            buf.append(line)
    flush()
    return headings, sections


def extract_page(html: str, url: str, rank: int) -> ScrapedPage | None:
    """Extract main content; returns None when nothing meaningful is found."""
    markdown = trafilatura.extract(
        html,
        output_format="markdown",
        include_comments=False,
        include_tables=False,
        favor_precision=True,
        url=url,
    )
    if not markdown:
        return None
    headings, sections = parse_markdown_sections(markdown)
    if not sections:
        return None
    meta = trafilatura.extract_metadata(html)
    title = (meta.title if meta and meta.title else "") or next(
        (h.text for h in headings if h.level == 1), ""
    )
    words = sum(len(s.text.split()) for s in sections)
    return ScrapedPage(
        url=url, rank=rank, title=title.strip(), headings=headings, sections=sections,
        word_count=words,
    )  # fmt: skip


class RobotsCache:
    """Per-origin robots.txt cache. Fails open when robots.txt is unreachable."""

    def __init__(self, client: httpx.AsyncClient, user_agent: str) -> None:
        self._client, self._ua = client, user_agent
        self._parsers: dict[str, RobotFileParser] = {}

    async def allowed(self, url: str) -> bool:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._parsers:
            rp = RobotFileParser()
            lines: list[str] = []
            try:
                r = await self._client.get(f"{origin}/robots.txt", timeout=4.0)
                if r.status_code == 200 and "html" not in r.headers.get("content-type", ""):
                    lines = r.text.splitlines()
            except httpx.HTTPError:
                pass
            rp.parse(lines)
            rp.modified()  # mark as checked, otherwise can_fetch() denies everything
            self._parsers[origin] = rp
        return self._parsers[origin].can_fetch(self._ua, url)


async def _scrape_one(
    result: SerpResult,
    client: httpx.AsyncClient,
    robots: RobotsCache,
    sem: asyncio.Semaphore,
    settings: Settings,
) -> ScrapedPage | None:
    async with sem:
        try:
            if not await robots.allowed(result.url):
                log.info("skip (robots.txt)", extra={"extra_fields": {"url": result.url}})
                return None
            resp = await client.get(result.url, timeout=settings.scrape_timeout)
            if resp.status_code != 200:
                log.info("skip (http %s)", resp.status_code)
                return None
            if "html" not in resp.headers.get("content-type", "html").lower():
                return None
            if len(resp.content) > settings.max_page_bytes:
                return None
            page = await asyncio.to_thread(extract_page, resp.text, result.url, result.rank)
        except (httpx.HTTPError, ValueError) as exc:
            log.info("skip (%s)", type(exc).__name__, extra={"extra_fields": {"url": result.url}})
            return None
        if page is None or page.word_count < settings.min_page_words:
            return None
        if not page.title:
            page.title = result.title
        return page


async def scrape_pages(
    results: list[SerpResult],
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[ScrapedPage]:
    """Fetch and extract pages in parallel; drop failures; need >= min_pages successes."""
    settings = settings or get_settings()
    owns = client is None
    client = client or guarded_client(
        enabled=settings.block_private_hosts,
        headers={"User-Agent": settings.user_agent, "Accept": "text/html,*/*;q=0.8"},
    )
    try:
        robots = RobotsCache(client, settings.user_agent)
        sem = asyncio.Semaphore(settings.scrape_concurrency)
        pages = await asyncio.gather(
            *[_scrape_one(r, client, robots, sem, settings) for r in results]
        )
    finally:
        if owns:
            await client.aclose()
    ok = sorted((p for p in pages if p), key=lambda p: p.rank)
    if len(ok) < settings.min_pages:
        raise ScrapeError(
            f"Only {len(ok)} of {len(results)} competitor pages could be read; "
            f"at least {settings.min_pages} are needed. Try a different keyword."
        )
    return ok
