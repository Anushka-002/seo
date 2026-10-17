import pytest
from pydantic import ValidationError

from app.models import Analysis, CacheEntry
from app.schemas.analysis import AnalyzeRequest

WORDS = " ".join(["word"] * 150)


def test_analysis_roundtrip(db):
    a = Analysis(keyword="best running shoes", draft_text=WORDS)
    db.add(a)
    db.commit()
    got = db.get(Analysis, a.id)
    assert got.status == "pending" and got.score is None and got.created_at is not None


def test_cache_entry_roundtrip(db):
    db.add(CacheEntry(key="abc", kind="serp", payload={"results": []}))
    db.commit()
    assert db.get(CacheEntry, "abc").payload == {"results": []}


def test_request_accepts_text():
    r = AnalyzeRequest(keyword="  best   running shoes ", draft_text=WORDS)
    assert r.keyword == "best running shoes"


def test_request_accepts_url():
    assert AnalyzeRequest(keyword="seo tips", draft_url="https://example.com/post")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"keyword": "x", "draft_text": WORDS},
        {"keyword": "seo tips"},
        {"keyword": "seo tips", "draft_text": WORDS, "draft_url": "https://example.com"},
        {"keyword": "seo tips", "draft_text": "too short"},
        {"keyword": "seo tips", "draft_text": " ".join(["w"] * 20_001)},
        {"keyword": "seo tips", "draft_url": "not-a-url"},
    ],
)
def test_request_rejects_bad_input(kwargs):
    with pytest.raises(ValidationError):
        AnalyzeRequest(**kwargs)


def test_request_accepts_optional_title_and_meta():
    r = AnalyzeRequest(
        keyword="seo tips", draft_text=WORDS, draft_title="A title", meta_description="A meta"
    )
    assert r.draft_title == "A title" and r.meta_description == "A meta"
    with pytest.raises(ValidationError):
        AnalyzeRequest(keyword="seo tips", draft_text=WORDS, draft_title="x" * 201)
