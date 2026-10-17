import numpy as np
import pytest

from app.rag.chunking import Chunk
from app.rag.keyphrases import extract_competitor_keyphrases, mark_draft_coverage
from app.rag.topics import (
    EMPTY_RATIO,
    FULL_RATIO,
    GAP_RATIO,
    choose_k,
    coverage_from_ratio,
    discover_topics,
    measure_coverage,
)
from app.services.scraper import ScrapedPage, Section


def _page(rank: int, text: str) -> ScrapedPage:
    return ScrapedPage(
        url=f"https://p{rank}.test/",
        rank=rank,
        title="t",
        headings=[],
        sections=[Section(heading="", level=0, text=text)],
        word_count=len(text.split()),
    )


# ---- keyphrases
def test_phrases_need_cross_page_agreement_and_exclude_keyword_words():
    common = "Midsole foam absorbs impact. Heel counter holds the foot."
    pages = [_page(1, common + " Alpha."), _page(2, common + " Beta."), _page(3, "Unrelated text.")]
    got = {k.phrase: k for k in extract_competitor_keyphrases(pages, "running shoes", 0.5)}
    assert "midsole foam absorbs impact" not in got  # >3 words never produced
    assert "foam absorbs impact" in got and got["foam absorbs impact"].pages == 2
    assert all("running" not in p for p in got)


def test_ngrams_do_not_cross_sentences_or_lines():
    pages = [
        _page(i, "Heading about fit\nCushioning matters. Rotating pairs helps.") for i in (1, 2, 3)
    ]
    phrases = {k.phrase for k in extract_competitor_keyphrases(pages, "zzz")}
    assert not any("fit cushioning" in p or "matters rotating" in p for p in phrases)


def test_stopword_free_and_readable_surface_forms():
    pages = [_page(i, "Choosing shoes. Impact on long runs matters. Shoe fit.") for i in (1, 2, 3)]
    phrases = {k.phrase for k in extract_competitor_keyphrases(pages, "zzz")}
    assert all(p not in {"impact on long"} for p in phrases)
    assert "choosing shoes" in phrases  # surface form, not the stem


def test_subsumed_shorter_phrase_dropped_and_few_pages_returns_empty():
    pages = [_page(i, "Carbon plated racing shoes are fast.") for i in (1, 2, 3)]
    phrases = [k.phrase for k in extract_competitor_keyphrases(pages, "zzz")]
    assert "carbon plated racing" in phrases or "plated racing shoes" in phrases
    assert "carbon plated" not in phrases
    assert extract_competitor_keyphrases(pages[:1], "zzz") == []


def test_mark_draft_coverage():
    pages = [_page(i, "Foam absorbs impact well.") for i in (1, 2, 3)]
    phr = extract_competitor_keyphrases(pages, "zzz")
    marked = mark_draft_coverage(phr, "this foam absorbs impact nicely")
    assert any(p.in_draft for p in marked) and phr[0].in_draft is False


# ---- topics
def _blobs(n_blobs: int, per: int = 8, dim: int = 16, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    centers = np.eye(dim)[:n_blobs] * 5
    pts = np.vstack([c + rng.normal(0, 0.15, (per, dim)) for c in centers])
    return pts / np.linalg.norm(pts, axis=1, keepdims=True)


@pytest.mark.parametrize("true_k", [4, 5, 7])
def test_choose_k_recovers_cluster_count(true_k):
    k, labels = choose_k(_blobs(true_k))
    assert k == true_k and len(set(labels)) == true_k


def test_choose_k_is_deterministic_and_handles_tiny_inputs():
    m = _blobs(5)
    assert np.array_equal(choose_k(m)[1], choose_k(m)[1])
    assert choose_k(m[:1])[0] == 1
    k, labels = choose_k(m[:3])
    assert 1 <= k <= 2 and len(labels) == 3


def _chunks(spec):
    """spec: list of (page, heading, is_intro)."""
    return [
        Chunk(id=f"c{i}", text=f"text {i}", source_url=f"https://p{p}.test/", rank=p,
              heading=h, chunk_index=i, is_intro=intro)
        for i, (p, h, intro) in enumerate(spec)
    ]  # fmt: skip


def test_discover_topics_skips_intro_and_single_page_clusters():
    # 5 blobs x 8 chunks; blob0 = intro text on every page, blob1 = only page 1, rest = 4 pages
    m = _blobs(5)
    spec = []
    for blob in range(5):
        for j in range(8):
            page = 1 if blob == 1 else (j % 4) + 1
            spec.append((page, "Intro" if blob == 0 else f"Topic {blob}", blob == 0))
    clusters = discover_topics(_chunks(spec), m, "kw", n_pages=4)
    labels = {c.label for c in clusters}
    assert labels == {"Topic 2", "Topic 3", "Topic 4"}
    assert all(c.page_share == 1.0 and c.label_source == "heading" for c in clusters)
    assert [c.id for c in clusters] == list(range(len(clusters)))
    assert all(0 < c.reference_sim <= 1.0001 for c in clusters)


def test_label_falls_back_to_terms_without_headings():
    m = _blobs(4)
    spec = [(j % 3 + 1, "", False) for j in range(len(m))]
    chunks = _chunks(spec)
    for i, c in enumerate(chunks):  # give each cluster distinctive words
        object.__setattr__(c, "text", f"blob{i // 8}word blob{i // 8}word extra")
    clusters = discover_topics(chunks, m, "kw", n_pages=3)
    assert clusters and all(c.label_source == "terms" and c.label for c in clusters)


def test_coverage_from_ratio_is_monotonic_and_bounded():
    xs = np.linspace(0, 1.3, 40)
    ys = [coverage_from_ratio(float(x)) for x in xs]
    assert ys == sorted(ys) and ys[0] == 0.0 and ys[-1] == 1.0
    assert coverage_from_ratio(EMPTY_RATIO) == 0.0 and coverage_from_ratio(FULL_RATIO) == 1.0
    assert EMPTY_RATIO < GAP_RATIO < FULL_RATIO


def test_measure_coverage_empty_draft_is_all_gaps():
    m = _blobs(4)
    spec = [(j % 3 + 1, f"T{j // 8}", False) for j in range(len(m))]
    clusters = discover_topics(_chunks(spec), m, "kw", 3)
    out = measure_coverage(clusters, np.zeros((0, m.shape[1])))
    assert out and all(cov == 0.0 and gap for _, cov, gap in out)


def test_measure_coverage_draft_close_to_centroid_is_covered():
    m = _blobs(4)
    spec = [(j % 3 + 1, f"T{j // 8}", False) for j in range(len(m))]
    clusters = discover_topics(_chunks(spec), m, "kw", 3)
    draft = np.vstack([c.centroid for c in clusters])
    assert all(not gap and cov == 1.0 for _, cov, gap in measure_coverage(clusters, draft))
