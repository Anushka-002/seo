from pathlib import Path

import pytest

from app.rag.analyzer import analyze_draft
from app.rag.draft import Draft, parse_draft_text
from app.rag.embeddings import HashingEmbedder
from app.rag.keyphrases import Keyphrase
from app.rag.scoring import (
    WEIGHTS,
    check_placement,
    flesch,
    score_keyword_coverage,
    score_placement,
    score_readability,
    score_structure,
    score_topic_coverage,
    structure_metrics,
    total_score,
)
from app.schemas.result import AnalysisResult, StructureMetrics
from app.services.ingest import build_index
from app.services.scraper import extract_page
from app.services.serp import SerpData, SerpResult

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data"
KW = "best running shoes"


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


# ---- placement
def _draft(**kw) -> Draft:
    base = dict(text="best running shoes are great. " * 5, source="text")
    base.update(kw)
    return Draft(**base)


def _status(checks):
    return {c.element: c.status for c in checks}


def test_placement_exact_partial_missing_not_provided():
    d = _draft(title="Best Running Shoes", meta_description="shoes for running and best picks")
    s = _status(check_placement(KW, d))
    assert s == {
        "title": "exact",
        "h1": "not_provided",
        "first_100_words": "exact",
        "meta_description": "partial",
    }


def test_h1_missing_vs_not_provided():
    from app.services.scraper import Heading

    with_headings = _draft(headings=[Heading(level=2, text="Part")])
    assert _status(check_placement(KW, with_headings))["h1"] == "missing"
    assert _status(check_placement(KW, _draft(source="url")))["h1"] == "missing"
    assert _status(check_placement(KW, _draft()))["h1"] == "not_provided"


def test_placement_score_scales_to_available_elements():
    full = score_placement(check_placement(KW, _draft(
        title=KW, h1=KW, meta_description=KW)))  # fmt: skip
    assert full.score == 15.0
    only_body = score_placement(check_placement(KW, _draft()))
    assert only_body.score == 15.0 and "Not scored" in only_body.reason
    none = score_placement(check_placement(KW, _draft(text="nothing relevant here " * 10)))
    assert none.score == 0.0 and "Add the exact keyword" in none.reason


# ---- structure / readability / coverage components
def _m(**kw) -> StructureMetrics:
    base = dict(
        draft_words=1000, median_competitor_words=1000, draft_headings=8,
        median_competitor_headings=8, draft_readability=60.0, median_competitor_readability=60.0,
    )  # fmt: skip
    base.update(kw)
    return StructureMetrics(**base)


def test_structure_scoring():
    assert score_structure(_m()).score == 15.0
    short = score_structure(_m(draft_words=500)).score  # 0.5x the competitor median
    shorter = score_structure(_m(draft_words=350)).score  # 0.35x
    assert 0 < shorter < short < 15.0
    assert score_structure(_m(draft_words=100)).score == pytest.approx(6.0)  # length floor
    assert score_structure(_m(draft_words=100_000)).score < 15.0  # padding penalty
    no_heads = score_structure(_m(draft_headings=0))
    assert no_heads.score == pytest.approx(9.0) and "No headings detected" in no_heads.reason
    assert score_structure(_m(median_competitor_headings=0, draft_headings=0)).score == 15.0


def test_readability_bands():
    assert score_readability(_m()).score == 10.0
    assert score_readability(_m(draft_readability=69)).score == 10.0
    mid = score_readability(_m(draft_readability=30)).score
    assert 0 < mid < 10
    assert score_readability(_m(draft_readability=-20)).score == 0.0
    assert "harder" in score_readability(_m(draft_readability=10)).reason
    assert "simpler" in score_readability(_m(draft_readability=100)).reason


def test_flesch_orders_simple_before_dense_and_empty_is_zero():
    assert flesch("The cat sat. It was fun.") > flesch(
        "Notwithstanding methodological heterogeneity, longitudinal investigations demonstrate."
    )
    assert flesch("   ") == 0.0


def test_keyword_coverage_component():
    ph = [Keyphrase(phrase="a b", pages=5, page_share=1.0, in_draft=True),
          Keyphrase(phrase="c d", pages=3, page_share=0.6, in_draft=False)]  # fmt: skip
    c = score_keyword_coverage(ph)
    assert c.score == pytest.approx(20 * 1.0 / 1.6, abs=0.05) and "c d" in c.reason
    assert score_keyword_coverage([]).score == 10.0  # neutral


def test_topic_coverage_component_neutral_when_no_clusters():
    assert score_topic_coverage([], []).score == 15.0


def test_total_score_bounds():
    from app.schemas.analysis import ScoreComponent

    comps = [ScoreComponent(name="x", score=60, max_score=60, reason=""),
             ScoreComponent(name="y", score=60, max_score=60, reason="")]  # fmt: skip
    assert total_score(comps) == 100.0 and total_score([]) == 0.0


# ---- integration on the sample corpus
@pytest.fixture(scope="module")
def corpus():
    pages = []
    for i, f in enumerate(sorted((SAMPLE / "pages").glob("*.html")), 1):
        p = extract_page(f.read_text(encoding="utf-8"), f"https://{f.stem}/", i)
        if p and p.word_count >= 150:
            pages.append(p)
    serp = SerpData(
        keyword=KW, country="us",
        results=[SerpResult(rank=p.rank, title=p.title, url=p.url) for p in pages],
    )  # fmt: skip
    index = build_index(pages, HashingEmbedder())
    yield pages, serp, index
    index.close()


def _run(corpus, text, **kw) -> AnalysisResult:
    pages, serp, index = corpus
    return analyze_draft(
        keyword=KW, draft=parse_draft_text(text, **kw), pages=pages, serp=serp, index=index
    )


STRONG = (SAMPLE / "drafts" / "strong.md").read_text()
WEAK = (SAMPLE / "drafts" / "weak.txt").read_text()
META = {
    "title": "Best Running Shoes: Buyer's Guide",
    "meta_description": "How to pick running shoes",
}


def test_strong_draft_far_outscores_weak(corpus):
    strong, weak = _run(corpus, STRONG, **META), _run(corpus, WEAK)
    assert strong.score >= 70 and weak.score <= 25 and strong.score - weak.score > 50
    assert sum(t.is_gap for t in strong.topics) <= 1
    assert all(t.is_gap and t.coverage == 0.0 for t in weak.topics)


def test_result_is_consistent_and_serialisable(corpus):
    r = _run(corpus, STRONG, **META)
    assert r.score == pytest.approx(sum(c.score for c in r.components), abs=0.11)
    assert [c.name for c in r.components] == list(WEIGHTS)
    assert all(0 <= c.score <= c.max_score for c in r.components)
    assert r.n_clusters == len(r.topics) == 6 and r.embedder == "hashing"
    assert len(r.competitors) == 5 and r.competitors[0].rank == 1
    assert all(t.evidence_chunk_ids for t in r.topics)
    assert AnalysisResult.model_validate_json(r.model_dump_json()) == r


def test_analysis_is_deterministic(corpus):
    a, b = _run(corpus, STRONG, **META), _run(corpus, STRONG, **META)
    assert a.model_dump() == b.model_dump()


def test_gaps_sorted_first_by_severity(corpus):
    r = _run(corpus, STRONG.split("## Price and value")[0], **META)  # drop price + lifespan
    flags = [t.is_gap for t in r.topics]
    assert flags == sorted(flags, reverse=True) and any(flags)
    gap_labels = {t.label for t in r.topics if t.is_gap}
    assert {"Price and value", "How long running shoes last"} <= gap_labels


def test_adding_a_missing_section_raises_topic_score(corpus):
    base = _run(corpus, STRONG.split("## Price and value")[0], **META)
    full = _run(corpus, STRONG, **META)
    topic = lambda r: next(c for c in r.components if c.name == "Topic coverage").score  # noqa: E731
    assert topic(full) > topic(base)
    assert full.score > base.score


def test_pasting_competitor_text_verbatim_covers_topics(corpus):
    pages, _, _ = corpus
    verbatim = "\n\n".join(f"## {s.heading}\n\n{s.text}" for s in pages[0].sections if s.heading)
    r = _run(corpus, "# Best running shoes\n\n" + verbatim, **META)
    present = {s.heading for s in pages[0].sections}
    gaps = {t.label for t in r.topics if t.is_gap}
    # every topic the page really contains is covered; only topics it lacks may be gaps
    assert gaps == {t.label for t in r.topics} - present
    assert gaps == {"Price and value"}


def test_off_topic_draft_scores_low_and_does_not_crash(corpus):
    text = "Quarterly tax filing requires careful bookkeeping and receipts. " * 20
    r = _run(corpus, text)
    assert r.score < 30 and all(t.is_gap for t in r.topics)


def test_draft_with_no_chunks_does_not_crash(corpus):
    pages, serp, index = corpus
    empty = Draft(text="", sections=[])
    r = analyze_draft(keyword=KW, draft=empty, pages=pages, serp=serp, index=index)
    assert r.score <= 20 and all(t.is_gap for t in r.topics)


def test_structure_metrics_use_competitor_medians(corpus):
    pages, _, _ = corpus
    m = structure_metrics(parse_draft_text(STRONG), pages)
    assert 300 <= m.median_competitor_words <= 330 and m.median_competitor_headings == 6
    assert m.draft_headings == 7


def test_result_carries_the_drafts_own_title_and_meta(corpus):
    r = _run(corpus, STRONG, **META)
    assert r.draft_title == META["title"] and r.draft_meta_description == META["meta_description"]
    plain = _run(corpus, WEAK)
    assert plain.draft_title is None and plain.draft_meta_description is None
