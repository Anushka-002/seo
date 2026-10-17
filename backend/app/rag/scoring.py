"""Deterministic SEO score (0-100). No LLM involved: same input -> same score."""

import math
from statistics import median

import textstat

from app.rag.draft import Draft
from app.rag.intent import IntentResult
from app.rag.keyphrases import Keyphrase
from app.rag.text_utils import contains_all_terms, contains_phrase, first_words
from app.rag.topics import TopicCluster
from app.schemas.analysis import ScoreComponent
from app.schemas.result import PlacementCheck, StructureMetrics
from app.services.scraper import ScrapedPage

WEIGHTS = {
    "Topic coverage": 30,
    "Keyword & phrase coverage": 20,
    "Keyword placement": 15,
    "Structure & length": 15,
    "Search intent match": 10,
    "Readability": 10,
}
PLACEMENT_POINTS = {"title": 4.0, "h1": 4.0, "first_100_words": 4.0, "meta_description": 3.0}


def _component(name: str, fraction: float, reason: str) -> ScoreComponent:
    fraction = min(1.0, max(0.0, fraction))
    return ScoreComponent(
        name=name, score=round(WEIGHTS[name] * fraction, 1), max_score=WEIGHTS[name], reason=reason
    )


def _join(items: list[str], limit: int = 3) -> str:
    shown = ", ".join(items[:limit])
    return shown + (f" (+{len(items) - limit} more)" if len(items) > limit else "")


def flesch(text: str) -> float:
    """Flesch reading ease (higher = easier). Empty text -> 0."""
    return float(textstat.flesch_reading_ease(text)) if text.strip() else 0.0


def score_topic_coverage(
    clusters: list[TopicCluster], coverages: list[tuple[float, float, bool]]
) -> ScoreComponent:
    """Share-weighted coverage of subtopics that several competitors agree on."""
    if not clusters:
        return _component(
            "Topic coverage", 0.5, "Competitors share no common subtopics; scored neutral."
        )
    weights = [c.page_share for c in clusters]
    frac = sum(w * cov for w, (_, cov, _) in zip(weights, coverages, strict=True)) / sum(weights)
    gaps = [c.label for c, (_, _, gap) in zip(clusters, coverages, strict=True) if gap]
    covered = len(clusters) - len(gaps)
    reason = f"Covers {covered} of {len(clusters)} subtopics competitors share."
    if gaps:
        reason += f" Missing: {_join(gaps)}."
    return _component("Topic coverage", frac, reason)


def score_keyword_coverage(phrases: list[Keyphrase]) -> ScoreComponent:
    """Share-weighted use of phrases that most competitors include."""
    if not phrases:
        return _component(
            "Keyword & phrase coverage", 0.5, "No common competitor phrases found; scored neutral."
        )
    total = sum(p.page_share for p in phrases)
    frac = sum(p.page_share for p in phrases if p.in_draft) / total
    missing = [p.phrase for p in phrases if not p.in_draft]
    used = len(phrases) - len(missing)
    reason = f"Uses {used} of {len(phrases)} phrases common across competitors."
    if missing:
        reason += f" Missing: {_join(missing, 4)}."
    return _component("Keyword & phrase coverage", frac, reason)


def check_placement(keyword: str, draft: Draft) -> list[PlacementCheck]:
    """Is the target keyword in the title, H1, first 100 words and meta description?"""

    def status(text: str | None, provided: bool) -> tuple[bool, str]:
        if not provided or not text:
            return False, "not_provided"
        if contains_phrase(text, keyword):
            return True, "exact"
        if contains_all_terms(text, keyword):
            return True, "partial"
        return True, "missing"

    has_structure = draft.source == "url" or bool(draft.headings)
    rows = [
        ("title", *status(draft.title, draft.has_title)),
        ("h1", *status(draft.h1, bool(draft.h1) or has_structure)),
        ("first_100_words", *status(first_words(draft.text, 100), True)),
        ("meta_description", *status(draft.meta_description, bool(draft.meta_description))),
    ]
    out = []
    for element, available, st in rows:
        if element == "h1" and has_structure and not draft.h1:
            available, st = True, "missing"
        out.append(PlacementCheck(element=element, available=available, status=st))
    return out


def score_placement(checks: list[PlacementCheck]) -> ScoreComponent:
    """Exact = full credit, all terms present = half; unavailable elements are not scored."""
    credit = {"exact": 1.0, "partial": 0.5, "missing": 0.0}
    avail = [c for c in checks if c.available]
    possible = sum(PLACEMENT_POINTS[c.element] for c in avail)
    earned = sum(PLACEMENT_POINTS[c.element] * credit[c.status] for c in avail)
    names = {"title": "title", "h1": "H1", "first_100_words": "first 100 words",
             "meta_description": "meta description"}  # fmt: skip
    ok = [names[c.element] for c in avail if c.status == "exact"]
    bad = [names[c.element] for c in avail if c.status in ("missing", "partial")]
    skipped = [names[c.element] for c in checks if not c.available]
    parts = []
    if ok:
        parts.append(f"Keyword present in {_join(ok, 4)}.")
    if bad:
        parts.append(f"Add the exact keyword to: {_join(bad, 4)}.")
    if skipped:
        parts.append(f"Not scored (not provided): {_join(skipped, 4)}.")
    return _component("Keyword placement", earned / possible if possible else 0.0, " ".join(parts))


def structure_metrics(draft: Draft, pages: list[ScrapedPage]) -> StructureMetrics:
    """Draft vs competitor medians for length, headings and readability."""
    body = lambda p: "\n\n".join(s.text for s in p.sections)  # noqa: E731
    return StructureMetrics(
        draft_words=draft.word_count,
        median_competitor_words=int(median(p.word_count for p in pages)),
        draft_headings=len(draft.headings),
        median_competitor_headings=int(median(len(p.headings) for p in pages)),
        draft_readability=round(flesch(draft.text), 1),
        median_competitor_readability=round(median(flesch(body(p)) for p in pages), 1),
    )


def _length_fraction(ratio: float) -> float:
    if ratio >= 2.5:
        return 0.85  # far longer than every competitor: slight penalty for padding
    if ratio >= 0.9:
        return 1.0
    return max(0.0, (ratio - 0.3) / 0.6)


def score_structure(m: StructureMetrics) -> ScoreComponent:
    """9 points for length vs competitor median, 6 for heading count vs competitor median."""
    ratio = m.draft_words / m.median_competitor_words if m.median_competitor_words else 1.0
    length = _length_fraction(ratio)
    if m.median_competitor_headings:
        heads = min(1.0, m.draft_headings / m.median_competitor_headings)
    else:
        heads = 1.0
    reason = (
        f"{m.draft_words} words vs competitor median {m.median_competitor_words}; "
        f"{m.draft_headings} headings vs median {m.median_competitor_headings}."
    )
    if m.draft_headings == 0:
        reason += " No headings detected (use #, ##, ### markers or paste a URL)."
    elif length < 1.0:
        reason += " Consider expanding the content."
    return _component("Structure & length", (9 * length + 6 * heads) / 15, reason)


def score_readability(m: StructureMetrics) -> ScoreComponent:
    """Full marks within +/-10 Flesch points of the competitor median (clamped to 30-70)."""
    target = min(70.0, max(30.0, m.median_competitor_readability))
    diff = abs(m.draft_readability - target)
    frac = 1.0 if diff <= 10 else max(0.0, 1.0 - (diff - 10) / 30)
    if diff <= 10:
        verdict = "on target"
    elif m.draft_readability < target:
        verdict = "harder to read than competitors"
    else:
        verdict = "simpler than competitors"
    return _component(
        "Readability",
        frac,
        f"Flesch reading ease {m.draft_readability:.0f} vs target ~{target:.0f}: {verdict}.",
    )


def score_intent(match: float, serp: IntentResult, draft: IntentResult) -> ScoreComponent:
    """Does the draft read like the intent the SERP rewards?"""
    if serp.primary == draft.primary:
        reason = f"Draft and SERP both lean {serp.primary}."
    else:
        reason = (
            f"SERP leans {serp.primary} (cues: {_join(serp.cues, 3) or 'n/a'}); "
            f"draft reads {draft.primary}."
        )
    return _component("Search intent match", match, reason)


def total_score(components: list[ScoreComponent]) -> float:
    """Sum of component scores, 0-100, one decimal."""
    return round(min(100.0, max(0.0, math.fsum(c.score for c in components))), 1)
