"""End-to-end: HTTP API -> background LangGraph pipeline -> SSE, with mocked web + LLM."""

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, delete, text

from app.api import analyses as analyses_api
from app.api.analyses import get_owner
from app.core import db as db_mod
from app.core.config import Settings
from app.core.db import SessionLocal
from app.main import _mark_interrupted
from app.models import Analysis, CacheEntry
from app.rag.embeddings import HashingEmbedder
from app.schemas.result import AnalysisResult
from app.services.llm import LLMError
from app.services.progress import ProgressBroker
from app.services.ratelimit import RateLimiter
from tests.helpers import SAMPLE, FakeLLM, make_site, md_to_html

STRONG = (SAMPLE / "drafts" / "strong.md").read_text()
WEAK = (SAMPLE / "drafts" / "weak.txt").read_text()
KW = "best running shoes"


def cid() -> dict[str, str]:
    return {"X-Client-Id": uuid.uuid4().hex}


@pytest.fixture
def api(client, pages_html):
    rt = client.app.state.runtime
    with SessionLocal() as db:
        db.execute(delete(CacheEntry))
        db.commit()
    counters: dict = {}
    rt.settings = Settings(
        serper_api_key="test-key", embedder="hashing", block_private_hosts=False,
        groq_api_key="", database_url="sqlite://",
    )  # fmt: skip
    rt.embedder, rt.llm = HashingEmbedder(), FakeLLM()
    rt.http = httpx.AsyncClient(
        transport=httpx.MockTransport(make_site(pages_html, counters=counters))
    )
    client.app.state.limiter = RateLimiter(100)
    yield SimpleNamespace(c=client, rt=rt, counters=counters, h=cid(), pages=pages_html)


def post(api, headers=None, **body):
    body = {"keyword": KW, "draft_text": WEAK, **body}
    body = {k: v for k, v in body.items() if v is not None}
    return api.c.post("/api/analyze", json=body, headers=headers or api.h)


def wait(api, aid, headers=None, timeout=30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = api.c.get(f"/api/analyses/{aid}", headers=headers or api.h)
        assert r.status_code == 200, r.text
        if r.json()["status"] in ("done", "failed"):
            return r.json()
        time.sleep(0.05)
    raise AssertionError("analysis did not finish in time")


def sse(api, aid, headers=None) -> list[dict]:
    events, cur = [], {}
    with api.c.stream("GET", f"/api/analyses/{aid}/events", headers=headers or api.h) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache"
        for line in r.iter_lines():
            if line.startswith("event:"):
                cur["event"] = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                cur["data"] = json.loads(line.split(":", 1)[1])
            elif line == "" and cur:
                events.append(cur)
                cur = {}
    return events


# ---------------------------------------------------------------- happy paths
def test_full_analysis_with_pasted_draft(api):
    r = post(api)
    assert r.status_code == 202
    body = r.json()
    assert (
        body["status"] == "pending"
        and body["events_url"] == f"/api/analyses/{body['analysis_id']}/events"
    )
    detail = wait(api, body["analysis_id"])
    assert detail["status"] == "done" and detail["stage"] == "done" and detail["error"] is None
    assert "draft_text" not in detail  # drafts are never echoed back
    result = AnalysisResult.model_validate(detail["result"])
    assert detail["score"] == result.score and result.keyword == KW
    assert result.llm_status == "ok" and len(result.recommendations) == 6
    assert result.suggestions and result.suggestions.title_has_keyword
    assert all(
        set(rec.citations) <= {s.n for s in result.sources} for rec in result.recommendations
    )
    assert len(result.competitors) == 5


def test_strong_draft_scores_high_end_to_end(api):
    r = post(
        api,
        draft_text=STRONG,
        draft_title="Best Running Shoes: Guide",
        meta_description="How to choose the best running shoes.",
    )
    aid = r.json()["analysis_id"]
    d = wait(api, aid)
    assert d["status"] == "done" and d["score"] >= 70


def test_sse_streams_every_stage_in_order(api):
    aid = post(api).json()["analysis_id"]
    events = sse(api, aid)
    stages = [e["data"]["stage"] for e in events]
    for expected in (
        "queued",
        "searching",
        "scraping",
        "indexing",
        "analyzing",
        "generating",
        "done",
    ):
        assert expected in stages
    order = [
        s
        for s in stages
        if s in ("searching", "scraping", "indexing", "analyzing", "generating", "done")
    ]
    seen = []
    for s in order:
        if s not in seen:
            seen.append(s)
    assert seen == ["searching", "scraping", "indexing", "analyzing", "generating", "done"]
    pct = [e["data"]["progress"] for e in events]
    assert pct == sorted(pct) and pct[-1] == 100
    assert events[-1]["event"] == "done" and events[-1]["data"]["data"]["llm_status"] == "ok"
    assert [e["data"]["seq"] for e in events] == list(range(len(events)))


def test_sse_replays_after_completion_and_synthesises_when_history_is_gone(api):
    aid = post(api).json()["analysis_id"]
    wait(api, aid)
    assert sse(api, aid)[-1]["event"] == "done"  # replay from broker history
    api.rt.broker.forget(aid)
    events = sse(api, aid)  # e.g. after a restart: derived from the database row
    assert [e["event"] for e in events] == ["done"] and events[0]["data"]["data"][
        "score"
    ] is not None


def test_draft_url_is_fetched_and_excluded_from_competitors(api):
    api.rt.http = httpx.AsyncClient(transport=httpx.MockTransport(make_site(
        api.pages,
        extra_pages={"mydraft.test": (200, md_to_html(STRONG, "Best Running Shoes"))},
        organic_hosts=[*api.pages, "mydraft.test"],
    )))  # fmt: skip
    aid = post(api, draft_text=None, draft_url="https://mydraft.test/post").json()["analysis_id"]
    d = wait(api, aid)
    assert d["status"] == "done", d["error"]
    result = AnalysisResult.model_validate(d["result"])
    assert (
        all("mydraft.test" not in c.url for c in result.competitors)
        and len(result.competitors) == 5
    )
    assert result.structure.draft_headings >= 6 and result.score >= 60


def test_competitor_scrape_and_serp_are_cached_between_analyses(api):
    wait(api, post(api).json()["analysis_id"])
    first_pages = api.counters["pages"]
    wait(api, post(api, draft_text=STRONG).json()["analysis_id"])
    assert api.counters["serper"] == 1 and api.counters["pages"] == first_pages


def test_runs_without_llm_key_and_with_total_llm_failure(api):
    api.rt.llm = None  # no key configured -> get_llm raises -> graceful skip
    d = wait(api, post(api).json()["analysis_id"])
    result = AnalysisResult.model_validate(d["result"])
    assert d["status"] == "done" and result.llm_status == "skipped" and result.recommendations
    err = LLMError("The AI provider's rate limit or quota was reached. Try again shortly.")
    api.rt.llm = FakeLLM(gaps=err, seo=err)
    d2 = wait(api, post(api, draft_text=STRONG + " extra").json()["analysis_id"])
    assert d2["status"] == "done" and d2["result"]["llm_status"] == "failed"
    assert "rate limit" in d2["result"]["llm_message"]


def test_several_analyses_queue_and_all_finish(api):
    api.rt.semaphore = asyncio.Semaphore(1)
    ids = [post(api, draft_text=WEAK + f" variant {i}").json()["analysis_id"] for i in range(3)]
    assert all(wait(api, i)["status"] == "done" for i in ids)


# ---------------------------------------------------------------- failure paths
def test_serp_auth_failure_is_reported_without_leaking_details(api):
    api.rt.http = httpx.AsyncClient(
        transport=httpx.MockTransport(make_site(api.pages, serper_status=401))
    )
    aid = post(api).json()["analysis_id"]
    events = sse(api, aid)
    assert (
        events[-1]["event"] == "error" and "rejected the API key" in events[-1]["data"]["message"]
    )
    d = wait(api, aid)
    assert d["status"] == "failed" and "test-key" not in json.dumps(d) and d["result"] is None


def test_unreadable_competitors_fail_with_clear_message(api):
    api.rt.http = httpx.AsyncClient(
        transport=httpx.MockTransport(make_site({}, organic_hosts=["a.test", "b.test"]))
    )
    d = wait(api, post(api).json()["analysis_id"])
    assert d["status"] == "failed" and "competitor pages could be read" in d["error"]


@pytest.mark.parametrize(
    ("status", "html", "expect"),
    [
        (404, "", "HTTP 404"),
        (200, "<html><body><p>Tiny.</p></body></html>", "too little readable text"),
    ],
)
def test_bad_draft_url_fails_cleanly(api, status, html, expect):
    api.rt.http = httpx.AsyncClient(transport=httpx.MockTransport(make_site(
        api.pages, extra_pages={"mydraft.test": (status, html)})))  # fmt: skip
    aid = post(api, draft_text=None, draft_url="https://mydraft.test/x").json()["analysis_id"]
    d = wait(api, aid)
    assert d["status"] == "failed" and expect in d["error"]


def test_unexpected_crash_gives_generic_error_not_internals(api):
    class Boom:
        name, dim = "boom", 8

        def embed(self, texts):
            raise RuntimeError("secret internal detail /srv/app/token=abc")

    api.rt.embedder = Boom()
    d = wait(api, post(api).json()["analysis_id"])
    assert d["status"] == "failed" and "Something went wrong" in d["error"]
    assert "secret" not in d["error"] and "token" not in d["error"]


# ------------------------------------------------------------ request validation & abuse controls
@pytest.mark.parametrize(
    "body",
    [
        {"keyword": "x", "draft_text": WEAK},
        {"keyword": KW, "draft_text": "too short"},
        {"keyword": KW},
        {"keyword": KW, "draft_text": WEAK, "draft_url": "https://example.com/a"},
        {"keyword": KW, "draft_url": "javascript:alert(1)"},
    ],
)
def test_invalid_bodies_are_422_and_nothing_is_stored(api, body):
    assert api.c.post("/api/analyze", json=body, headers=api.h).status_code == 422
    assert api.c.get("/api/analyses", headers=api.h).json()["total"] == 0


@pytest.mark.parametrize(
    "headers", [{}, {"X-Client-Id": "short"}, {"X-Client-Id": "bad id with spaces!!"}]
)
def test_client_id_header_is_required_and_validated(api, headers):
    assert api.c.get("/api/analyses", headers=headers).status_code == 400
    assert (
        api.c.post(
            "/api/analyze", json={"keyword": KW, "draft_text": WEAK}, headers=headers
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "ftp://example.com/x",
    ],
)
def test_private_or_odd_draft_urls_are_rejected_up_front(api, url):
    api.rt.settings = api.rt.settings.model_copy(update={"block_private_hosts": True})
    r = post(api, draft_text=None, draft_url=url)
    assert r.status_code in (400, 422), r.text
    assert api.c.get("/api/analyses", headers=api.h).json()["total"] == 0


def test_rate_limit_returns_429_with_retry_after_and_stores_nothing(api):
    api.c.app.state.limiter = RateLimiter(2)
    assert [post(api).status_code for _ in range(2)] == [202, 202]
    r = post(api)
    assert (
        r.status_code == 429
        and int(r.headers["retry-after"]) >= 1
        and "Rate limit" in r.json()["detail"]
    )
    assert api.c.get("/api/analyses", headers=api.h).json()["total"] == 2


def test_rate_limit_ignores_spoofed_left_xff_entries(api):
    api.c.app.state.limiter = RateLimiter(1)
    first = post(api, headers={**cid(), "X-Forwarded-For": "6.6.6.6, 1.2.3.4"})
    second = post(api, headers={**cid(), "X-Forwarded-For": "7.7.7.7, 1.2.3.4"})  # same real client
    assert first.status_code == 202 and second.status_code == 429


# ---------------------------------------------------------------- history, ownership, demo rows
def test_owners_cannot_see_or_delete_each_others_analyses(api):
    aid = post(api).json()["analysis_id"]
    wait(api, aid)
    other = cid()
    assert api.c.get(f"/api/analyses/{aid}", headers=other).status_code == 404
    assert api.c.get(f"/api/analyses/{aid}/events", headers=other).status_code == 404
    assert api.c.delete(f"/api/analyses/{aid}", headers=other).status_code == 404
    assert api.c.get("/api/analyses", headers=other).json()["total"] == 0
    assert api.c.get(f"/api/analyses/{aid}", headers=api.h).status_code == 200


def test_delete_then_gone(api):
    aid = post(api).json()["analysis_id"]
    wait(api, aid)
    assert api.c.delete(f"/api/analyses/{aid}", headers=api.h).status_code == 204
    assert api.c.get(f"/api/analyses/{aid}", headers=api.h).status_code == 404
    assert api.c.delete(f"/api/analyses/{aid}", headers=api.h).status_code == 404


def test_demo_rows_are_readable_by_anyone_but_not_listed_or_deletable(api):
    with SessionLocal() as db:
        row = Analysis(
            keyword="demo kw", status="done", score=88.0, is_demo=True, owner=None, result={}
        )
        db.add(row)
        db.commit()
        demo_id = row.id
    other = cid()
    assert api.c.get(f"/api/analyses/{demo_id}", headers=other).status_code == 200
    assert api.c.get("/api/analyses", headers=other).json()["total"] == 0
    assert api.c.delete(f"/api/analyses/{demo_id}", headers=other).status_code == 404


def test_history_is_paginated_filtered_and_newest_first(api):
    owner = get_owner(api.h["X-Client-Id"])
    base = datetime.now(UTC)
    with SessionLocal() as db:
        for i, kw in enumerate(
            ["alpha shoes", "beta shoes", "gamma socks", "delta shoes", "epsilon hats"]
        ):
            db.add(Analysis(keyword=kw, status="done", score=float(i), owner=owner,
                            created_at=base + timedelta(seconds=i)))  # fmt: skip
        db.commit()
    page = api.c.get("/api/analyses?limit=2&offset=0", headers=api.h).json()
    assert page["total"] == 5 and [i["keyword"] for i in page["items"]] == [
        "epsilon hats",
        "delta shoes",
    ]
    page2 = api.c.get("/api/analyses?limit=2&offset=4", headers=api.h).json()
    assert [i["keyword"] for i in page2["items"]] == ["alpha shoes"]
    filt = api.c.get("/api/analyses?q=SHOES", headers=api.h).json()
    assert filt["total"] == 3 and all("shoes" in i["keyword"] for i in filt["items"])
    assert api.c.get("/api/analyses?limit=0", headers=api.h).status_code == 422
    assert api.c.get("/api/analyses?limit=101", headers=api.h).status_code == 422


# ---------------------------------------------------------------- lifecycle
def test_runs_interrupted_by_a_restart_are_marked_failed(api):
    with SessionLocal() as db:
        rows = [
            Analysis(keyword=f"k{i}", status=s, owner="o")
            for i, s in enumerate(["pending", "running", "done"])
        ]
        db.add_all(rows)
        db.commit()
        ids = [r.id for r in rows]
    assert _mark_interrupted() >= 2
    with SessionLocal() as db:
        got = {i: db.get(Analysis, i) for i in ids}
    assert [got[i].status for i in ids] == ["failed", "failed", "done"]
    assert "restarted" in got[ids[0]].error


def test_old_sqlite_files_get_new_columns_added(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.execute(
            text("CREATE TABLE analyses (id VARCHAR(36) PRIMARY KEY, keyword VARCHAR(200))")
        )
    monkeypatch.setattr(db_mod, "engine", eng)
    db_mod._ensure_columns()
    db_mod._ensure_columns()  # idempotent
    with eng.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(analyses)"))}
    assert {"owner", "draft_title", "meta_description"} <= cols


async def test_sse_sends_heartbeats_while_idle_and_ends_on_terminal_event(monkeypatch):
    monkeypatch.setattr(analyses_api, "HEARTBEAT_SECONDS", 0.05)
    rt = SimpleNamespace(broker=ProgressBroker())
    rt.broker.publish("hb", "queued", "q", 2)
    row = SimpleNamespace(status="running", score=None, error=None)
    stream = analyses_api._stream("hb", rt, row)
    first = await asyncio.wait_for(stream.__anext__(), 1)
    assert "event: progress" in first
    beat = await asyncio.wait_for(stream.__anext__(), 1)
    assert beat == ": keep-alive\n\n"
    rt.broker.publish("hb", "done", "d", 100, status="done")
    last = await asyncio.wait_for(stream.__anext__(), 1)
    assert "event: done" in last
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(stream.__anext__(), 1)


def test_openapi_lists_the_new_endpoints(api):
    paths = api.c.get("/api/openapi.json").json()["paths"]
    for p in (
        "/api/analyze",
        "/api/analyses",
        "/api/analyses/{analysis_id}",
        "/api/analyses/{analysis_id}/events",
    ):
        assert p in paths
