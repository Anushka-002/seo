import pytest

from app.rag.draft import draft_from_page, parse_draft_text
from app.rag.intent import (
    INTENTS,
    classify_draft_intent,
    classify_serp_intent,
    intent_match,
)
from app.rag.text_utils import (
    contains_all_terms,
    contains_phrase,
    first_words,
    stem,
    tokenize,
)
from app.services.scraper import extract_page
from app.services.serp import SerpData, SerpResult

BODY = " ".join(["word"] * 120)


def test_tokenize_and_stem():
    assert tokenize("Best Running-Shoes, 2026!") == ["best", "running", "shoes", "2026"]
    assert stem("shoes") == "shoe" and stem("studies") == "study"
    assert stem("class") == "class" and stem("bus") == "bus" and stem("is") == "is"


def test_contains_phrase_is_contiguous_and_plural_tolerant():
    assert contains_phrase("Our best running shoe picks", "best running shoes")
    assert not contains_phrase("best shoes for running", "best running shoes")
    assert not contains_phrase("anything", "")


def test_contains_all_terms_ignores_order_and_stopwords():
    assert contains_all_terms("shoes for running, the best", "best running shoes")
    assert not contains_all_terms("best shoes", "best running shoes")


def test_first_words():
    assert first_words("a b c d", 2) == "a b"


# ---- draft parsing
def test_plain_text_has_no_headings():
    d = parse_draft_text(BODY, title="  My Title ", meta_description="")
    assert d.title == "My Title" and d.meta_description is None
    assert d.headings == [] and d.h1 is None and d.word_count == 120
    assert d.sections == [("", BODY)]


def test_markdown_headings_detected():
    md = f"# Main Title\n\nIntro {BODY}\n\n## Part One\n\nText {BODY}\n\n### Sub\n\nMore"
    d = parse_draft_text(md)
    assert d.h1 == "Main Title"
    assert [(h.level, h.text) for h in d.headings] == [
        (1, "Main Title"),
        (2, "Part One"),
        (3, "Sub"),
    ]
    assert [h for h, _ in d.sections] == ["Main Title", "Part One", "Sub"]


def test_draft_from_scraped_page(pages_html):
    page = extract_page(pages_html["runnerlab.test"], "https://runnerlab.test/", 1)
    d = draft_from_page(page, meta_description="meta")
    assert d.source == "url" and d.title and d.h1 and d.meta_description == "meta"
    assert len(d.headings) == len(page.headings)


# ---- intent
def _serp(titles, snippets=None, paa=None):
    snippets = snippets or [""] * len(titles)
    return SerpData(
        keyword="k",
        country="us",
        results=[
            SerpResult(rank=i, title=t, url=f"https://x{i}.test/", snippet=s)
            for i, (t, s) in enumerate(zip(titles, snippets, strict=True), 1)
        ],
        people_also_ask=paa or [],
    )


def test_serp_intent_commercial():
    r = classify_serp_intent(
        "best laptops", _serp(["Best Laptops 2026", "Top 10 laptops reviewed"])
    )
    assert r.primary == "commercial" and r.confidence > 0.5
    assert abs(sum(r.scores.values()) - 1) < 1e-9 and set(r.scores) == set(INTENTS)


def test_serp_intent_informational_and_paa_boost():
    r = classify_serp_intent("how to tie a tie", _serp(["How to tie a tie: guide"], paa=["Why?"]))
    assert r.primary == "informational"


def test_serp_intent_transactional():
    r = classify_serp_intent("buy iphone cheap", _serp(["iPhone deals and discount prices"]))
    assert r.primary == "transactional"


def test_no_cues_defaults_to_informational_with_zero_confidence():
    r = classify_serp_intent("zzz", _serp(["qqq"]))
    assert r.primary == "informational" and r.confidence == 0.0


def test_draft_intent_uses_headings():
    d = parse_draft_text(f"# Best laptops compared\n\n{BODY}\n\n## Top picks and reviews\n\n{BODY}")
    assert classify_draft_intent(d).primary == "commercial"


def test_intent_match_bounds_and_ordering():
    com = classify_serp_intent("best x", _serp(["Best x reviews"]))
    inf = classify_serp_intent("how to x", _serp(["How to x guide"]))
    assert intent_match(com, com) == pytest.approx(1.0)
    assert 0 <= intent_match(com, inf) < intent_match(com, com)
