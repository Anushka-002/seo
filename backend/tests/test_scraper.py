import httpx
import pytest

from app.services.scraper import ScrapeError, extract_page, scrape_pages
from app.services.serp import SerpResult


def test_extract_page_structure_and_boilerplate_removed(pages_html):
    page = extract_page(pages_html["runnerlab.test"], "https://runnerlab.test/", 1)
    assert page.title.startswith("Best Running Shoes")
    assert [h.level for h in page.headings][0] == 1
    assert "How to choose cushioning" in [h.text for h in page.headings]
    assert page.word_count > 250
    assert "Copyright" not in page.text and "Login" not in page.text


def test_extract_page_returns_none_for_empty_html():
    assert extract_page("<html><body></body></html>", "https://x.test/", 1) is None


def _handler(pages_html, *, robots="", missing=(), non_html=()):
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots, headers={"content-type": "text/plain"})
        if host in missing:
            return httpx.Response(404)
        if host in non_html:
            return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
        return httpx.Response(
            200, text=pages_html[host], headers={"content-type": "text/html; charset=utf-8"}
        )

    return handler


def _results(pages_html):
    return [
        SerpResult(rank=i, title=h, url=f"https://{h}/post") for i, h in enumerate(pages_html, 1)
    ]


async def test_scrape_drops_thin_missing_and_non_html(pages_html, settings):
    handler = _handler(pages_html, missing={"milesmag.test"}, non_html={"trailtalk.test"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        # 6 results: 1 thin, 1 missing, 1 non-html -> 3 good; lower the bar to 3 for this test
        s = settings.model_copy(update={"min_pages": 3})
        pages = await scrape_pages(_results(pages_html), settings=s, client=client)
    hosts = {p.url.split("/")[2] for p in pages}
    assert hosts == {"runnerlab.test", "racereport.test", "dailyrun.test"}
    assert [p.rank for p in pages] == sorted(p.rank for p in pages)


async def test_scrape_raises_when_too_few_pages(pages_html, settings):
    handler = _handler(pages_html, missing={"milesmag.test", "trailtalk.test"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ScrapeError, match="at least 4"):
            await scrape_pages(_results(pages_html), settings=settings, client=client)


async def test_scrape_respects_robots_txt(pages_html, settings):
    robots = "User-agent: *\nDisallow: /post"
    handler = _handler(pages_html, robots=robots)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ScrapeError):  # everything is disallowed
            await scrape_pages(_results(pages_html), settings=settings, client=client)


async def test_scrape_allows_when_robots_missing(pages_html, settings):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200, text=pages_html[request.url.host], headers={"content-type": "text/html"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pages = await scrape_pages(_results(pages_html), settings=settings, client=client)
    assert len(pages) == 5


async def test_scrape_survives_network_errors(pages_html, settings):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "dailyrun.test":
            raise httpx.ConnectTimeout("boom")
        return httpx.Response(
            200, text=pages_html[request.url.host], headers={"content-type": "text/html"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pages = await scrape_pages(_results(pages_html), settings=settings, client=client)
    assert len(pages) == 4
