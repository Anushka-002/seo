import httpx
import pytest

from app.services import serp as serp_mod
from app.services.cache import get_cached, make_key, set_cached
from app.services.serp import SerpError, fetch_serp, is_scrapable

PAYLOAD = {
    "organic": [
        {"title": "A", "link": "https://a.test/x", "snippet": "sa"},
        {"title": "YT", "link": "https://www.youtube.com/watch?v=1"},
        {"title": "A dup", "link": "https://a.test/x"},
        {"title": "PDF", "link": "https://b.test/file.pdf"},
        {"title": "B", "link": "https://b.test/y"},
    ],
    "relatedSearches": [{"query": "best trail shoes"}],
    "peopleAlsoAsk": [{"question": "How long do shoes last?"}],
}


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_serper_parses_filters_and_ranks(settings):
    seen = {}

    def handler(request):
        seen["key"] = request.headers["x-api-key"]
        seen["body"] = request.content.decode()
        return httpx.Response(200, json=PAYLOAD)

    async with _client(handler) as c:
        data = await fetch_serp("best running shoes", "us", settings=settings, client=c)
    assert [r.url for r in data.results] == ["https://a.test/x", "https://b.test/y"]
    assert [r.rank for r in data.results] == [1, 2]
    assert data.related_searches == ["best trail shoes"]
    assert data.people_also_ask == ["How long do shoes last?"]
    assert seen["key"] == "test-key" and '"gl":"us"' in seen["body"].replace(" ", "")


@pytest.mark.parametrize(
    ("status", "text"), [(401, "rejected the API key"), (429, "rate limit"), (500, "HTTP 500")]
)
async def test_serper_errors_are_friendly_and_do_not_leak_key(settings, status, text):
    async with _client(lambda r: httpx.Response(status)) as c:
        with pytest.raises(SerpError, match=text) as exc:
            await fetch_serp("kw", "us", settings=settings, client=c)
    assert "test-key" not in str(exc.value)


async def test_empty_results_raise(settings):
    async with _client(lambda r: httpx.Response(200, json={"organic": []})) as c:
        with pytest.raises(SerpError, match="No usable"):
            await fetch_serp("kw", "us", settings=settings, client=c)


async def test_duckduckgo_fallback_when_no_key(settings, monkeypatch):
    s = settings.model_copy(update={"serper_api_key": ""})
    monkeypatch.setattr(
        serp_mod,
        "_ddg_sync",
        lambda kw, c: [{"title": "D", "href": "https://d.test/", "body": "b"}],
    )
    data = await fetch_serp("kw", "in", settings=s)
    assert data.results[0].url == "https://d.test/" and data.results[0].snippet == "b"


async def test_duckduckgo_failure_is_wrapped(settings, monkeypatch):
    s = settings.model_copy(update={"serper_api_key": ""})

    def boom(kw, c):
        raise RuntimeError("ratelimit")

    monkeypatch.setattr(serp_mod, "_ddg_sync", boom)
    with pytest.raises(SerpError, match="temporarily unavailable"):
        await fetch_serp("kw", "us", settings=s)


async def test_serp_is_cached_per_keyword(settings, db):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=PAYLOAD)

    async with _client(handler) as c:
        a = await fetch_serp("Best  Shoes", "us", settings=settings, client=c, db=db)
        b = await fetch_serp("best shoes", "us", settings=settings, client=c, db=db)
    assert len(calls) == 1 and a == b


def test_cache_key_normalises_and_varies_by_day_and_country():
    assert make_key("serp", "Best  Shoes", "US", "2026-01-01") == make_key(
        "serp", "best shoes", "us", "2026-01-01"
    )
    assert make_key("serp", "x", "us", "2026-01-01") != make_key("serp", "x", "us", "2026-01-02")
    assert make_key("serp", "x", "us", "2026-01-01") != make_key("serp", "x", "in", "2026-01-01")


def test_cache_roundtrip_and_none_db_is_noop(db):
    set_cached(db, "serp", "k", "us", {"a": 1})
    set_cached(db, "serp", "k", "us", {"a": 2})
    assert get_cached(db, "serp", "k", "us") == {"a": 2}
    assert get_cached(None, "serp", "k", "us") is None
    set_cached(None, "serp", "k", "us", {})


def test_is_scrapable():
    assert is_scrapable("https://example.com/post")
    assert not is_scrapable("https://m.youtube.com/watch")
    assert not is_scrapable("ftp://example.com/x")
    assert not is_scrapable("https://example.com/report.PDF")
