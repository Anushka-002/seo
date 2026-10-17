"""Dashboard aggregation, GET /api/dashboard/stats, list sorting and POST /api/demo."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete

from app.api.analyses import get_owner
from app.core.db import SessionLocal
from app.models import Analysis
from app.services import dashboard as agg
from app.services.demo import DEMO_ID

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def run(i: int, keyword: str, score: float | None, days: int = 0):
    return SimpleNamespace(
        id=f"r{i}", keyword=keyword, score=score, created_at=T0 + timedelta(days=days or i)
    )


def result(*gaps: str, covered: tuple[str, ...] = ()) -> dict:
    topics = [{"label": g, "is_gap": True} for g in gaps]
    return {"topics": topics + [{"label": c, "is_gap": False} for c in covered]}


# ---------------------------------------------------------------- pure aggregation
def test_score_trend_is_oldest_first_limited_and_skips_unscored():
    rows = [run(3, "c", 70), run(1, "a", 40.04), run(2, "b", None), run(4, "d", 90)]
    trend = agg.score_trend(rows, limit=3)
    assert [p["id"] for p in trend] == ["r1", "r3", "r4"]
    assert trend[0]["score"] == 40.0
    assert [p["id"] for p in agg.score_trend(rows, limit=2)] == ["r3", "r4"]


def test_top_keywords_merge_case_and_whitespace_and_rank_by_count():
    rows = [
        run(1, "Running Shoes", 40), run(2, "running   shoes", 60), run(3, "trail shoes", 90),
        run(4, "trail shoes", 80), run(5, "trail shoes", 70), run(6, "solo", 10), run(7, "x", None),
    ]  # fmt: skip
    top = agg.top_keywords(rows, limit=3)
    assert [(k["keyword"], k["count"]) for k in top] == [
        ("trail shoes", 3), ("running   shoes", 2), ("solo", 1)
    ]  # the most recent spelling is displayed
    assert top[0]["avg_score"] == 80.0 and top[1]["avg_score"] == 50.0


def test_common_gaps_count_once_per_analysis_and_report_share():
    results = [
        result("Price and value", "price and value ", "Fit", covered=("Cushioning",)),
        result("Fit"),
        result("Fit", "Trail"),
        None,
    ]
    gaps, sample = agg.common_gaps(results)
    assert sample == 3
    assert [(g["label"], g["count"]) for g in gaps] == [
        ("Fit", 3), ("Price and value", 1), ("Trail", 1)
    ]
    assert gaps[0]["share"] == 1.0 and gaps[1]["share"] == pytest.approx(0.333, abs=0.001)
    assert all(g["label"] != "Cushioning" for g in gaps)  # covered topics are not gaps


def test_common_gaps_empty():
    assert agg.common_gaps([]) == ([], 0)
    assert agg.common_gaps([None, {}]) == ([], 0)  # no payload -> not an analysis
    assert agg.common_gaps([{"topics": []}]) == ([], 1)  # analysed, but no gaps


# ---------------------------------------------------------------- HTTP
@pytest.fixture
def owner():
    """A fresh anonymous browser identity and its hashed owner column value."""
    cid = uuid.uuid4().hex
    return SimpleNamespace(headers={"X-Client-Id": cid}, hashed=get_owner(cid))


@pytest.fixture(autouse=True)
def clean_rows():
    with SessionLocal() as db:
        db.execute(delete(Analysis))
        db.commit()
    yield


def add(owner_hash, keyword, score, days, *, status="done", gaps=(), demo=False):
    with SessionLocal() as db:
        db.add(Analysis(
            keyword=keyword, status=status, score=score, owner=owner_hash, is_demo=demo,
            created_at=T0 + timedelta(days=days), result=result(*gaps) if status == "done" else None,
        ))  # fmt: skip
        db.commit()


def test_stats_empty_state(client, owner):
    r = client.get("/api/dashboard/stats", headers=owner.headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total_analyses"] == 0 and body["avg_score"] is None
    assert body["score_trend"] == [] and body["top_keywords"] == [] and body["common_gaps"] == []
    assert body["score_change"] is None and body["gap_sample_size"] == 0


def test_stats_require_client_id(client):
    assert client.get("/api/dashboard/stats").status_code == 400


def test_stats_aggregate_only_my_finished_non_demo_runs(client, owner):
    add(owner.hashed, "running shoes", 40, 1, gaps=("Fit", "Price"))
    add(owner.hashed, "Running Shoes", 70, 2, gaps=("Fit",))
    add(owner.hashed, "trail shoes", 60, 3, gaps=())
    add(owner.hashed, "pending one", None, 4, status="pending")
    add(owner.hashed, "failed one", None, 5, status="failed")
    add(owner.hashed, "demo", 99, 6, demo=True)
    add("someone-else", "other person", 95, 7, gaps=("Secret",))
    body = client.get("/api/dashboard/stats", headers=owner.headers).json()
    assert body["total_analyses"] == 3
    assert body["avg_score"] == 56.7 and body["best_score"] == 70.0
    assert [p["score"] for p in body["score_trend"]] == [40.0, 70.0, 60.0]
    assert body["latest_score"] == 60.0 and body["score_change"] == 20.0
    assert body["top_keywords"][0] == {"keyword": "Running Shoes", "count": 2, "avg_score": 55.0}
    assert [(g["label"], g["count"]) for g in body["common_gaps"]] == [("Fit", 2), ("Price", 1)]
    assert body["gap_sample_size"] == 3
    assert "Secret" not in str(body) and "other person" not in str(body)


def test_history_search_and_sort(client, owner):
    add(owner.hashed, "alpha shoes", 30, 1)
    add(owner.hashed, "beta socks", 90, 2)
    add(owner.hashed, "gamma shoes", 60, 3)

    def kws(**params):
        r = client.get("/api/analyses", params=params, headers=owner.headers)
        assert r.status_code == 200, r.text
        return [i["keyword"] for i in r.json()["items"]]

    assert kws() == ["gamma shoes", "beta socks", "alpha shoes"]  # newest first by default
    assert kws(sort="score", order="desc") == ["beta socks", "gamma shoes", "alpha shoes"]
    assert kws(sort="score", order="asc") == ["alpha shoes", "gamma shoes", "beta socks"]
    assert kws(sort="keyword", order="asc") == ["alpha shoes", "beta socks", "gamma shoes"]
    assert kws(q="shoes", sort="score", order="desc") == ["gamma shoes", "alpha shoes"]
    bad = client.get("/api/analyses", params={"sort": "owner"}, headers=owner.headers)
    assert bad.status_code == 422  # only whitelisted columns can be sorted on


def test_demo_is_instant_shared_and_not_deletable(client, owner):
    r = client.post("/api/demo")
    assert r.status_code == 200
    body = r.json()
    assert body["analysis_id"] == DEMO_ID and body["status"] == "done"
    again = client.post("/api/demo")  # idempotent: still exactly one demo row
    assert again.json()["analysis_id"] == DEMO_ID
    with SessionLocal() as db:
        assert db.query(Analysis).filter(Analysis.is_demo.is_(True)).count() == 1
    d = client.get(f"/api/analyses/{DEMO_ID}", headers=owner.headers)
    assert d.status_code == 200
    detail = d.json()
    assert detail["is_demo"] is True and detail["status"] == "done"
    assert detail["result"]["keyword"] and 0 <= detail["result"]["score"] <= 100
    other = {"X-Client-Id": uuid.uuid4().hex}
    assert client.get(f"/api/analyses/{DEMO_ID}", headers=other).status_code == 200
    assert client.delete(f"/api/analyses/{DEMO_ID}", headers=owner.headers).status_code == 404
    listed = client.get("/api/analyses", headers=owner.headers).json()
    assert listed["total"] == 0  # the demo never pollutes anyone's history


def test_demo_unavailable_returns_503(client, monkeypatch):
    from app.services import demo

    monkeypatch.setattr(demo, "DEMO_FILE", demo.DEMO_FILE.with_name("missing.json"))
    demo.load_demo_result.cache_clear()
    try:
        assert client.post("/api/demo").status_code == 503
    finally:
        demo.load_demo_result.cache_clear()
