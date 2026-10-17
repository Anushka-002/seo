"""Competitor keyphrases by cross-page frequency, and draft coverage of them."""

import math
import re
from collections import Counter

from pydantic import BaseModel

from app.rag.text_utils import STOPWORDS, contains_phrase, stem, stems, tokenize
from app.services.scraper import ScrapedPage

MAX_PHRASES = 25
MAX_UNIGRAMS = 8


class Keyphrase(BaseModel):
    """A phrase that many competitors use, and whether the draft has it."""

    phrase: str
    pages: int  # number of competitor pages containing it
    page_share: float
    in_draft: bool = False


_SEGMENT = re.compile(r"[.!?;:,\n()\[\]\"\u201c\u201d\u2014\u2013|]+")


def _candidate_ngrams(text: str) -> dict[tuple[str, ...], str]:
    """Distinct stemmed 1-3 grams -> a readable surface form.

    N-grams never cross sentence, comma or line boundaries, and never contain a stopword.
    """
    out: dict[tuple[str, ...], str] = {}
    for segment in _SEGMENT.split(text):
        toks = tokenize(segment)
        for n in (1, 2, 3):
            for i in range(len(toks) - n + 1):
                gram = toks[i : i + n]
                if any(t in STOPWORDS for t in gram):
                    continue  # keeps phrases clean: "foam absorbs impact", not "impact on long"
                if any(t.isdigit() for t in gram):
                    continue
                if any(len(t) < 3 for t in gram):
                    continue
                if n == 1 and len(gram[0]) < 4:
                    continue
                out.setdefault(tuple(stem(t) for t in gram), " ".join(gram))
    return out


def extract_competitor_keyphrases(
    pages: list[ScrapedPage], keyword: str, min_share: float = 0.4
) -> list[Keyphrase]:
    """Phrases used by >= min_share of pages (at least 2), longest/most common first."""
    if len(pages) < 2:
        return []
    kw_stems = set(stems(keyword))
    df: Counter[tuple[str, ...]] = Counter()
    surfaces: dict[tuple[str, ...], Counter[str]] = {}
    for page in pages:
        grams = _candidate_ngrams(page.text)
        df.update(grams.keys())
        for g, surface in grams.items():
            surfaces.setdefault(g, Counter())[surface] += 1
    need = max(2, math.ceil(min_share * len(pages)))
    cands = {g: c for g, c in df.items() if c >= need and not set(g) <= kw_stems}
    # Unigrams must be near-universal; otherwise generic words flood the list.
    cands = {g: c for g, c in cands.items() if len(g) > 1 or c >= math.ceil(0.6 * len(pages))}
    # Drop a phrase when a longer one containing it is almost as common (keeps the specific one).
    keep: dict[tuple[str, ...], int] = {}
    for g, c in cands.items():
        subsumed = any(
            len(h) > len(g)
            and d >= 0.8 * c
            and any(h[i : i + len(g)] == g for i in range(len(h) - len(g) + 1))
            for h, d in cands.items()
        )
        if not subsumed:
            keep[g] = c
    ranked = sorted(keep.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    out: list[Keyphrase] = []
    unigrams = 0
    for g, c in ranked:
        if len(g) == 1:
            if unigrams >= MAX_UNIGRAMS:
                continue
            unigrams += 1
        phrase = surfaces[g].most_common(1)[0][0]
        out.append(Keyphrase(phrase=phrase, pages=c, page_share=c / len(pages)))
        if len(out) == MAX_PHRASES:
            break
    return out


def mark_draft_coverage(phrases: list[Keyphrase], draft_text: str) -> list[Keyphrase]:
    """Return copies of the phrases with in_draft set."""
    return [
        p.model_copy(update={"in_draft": contains_phrase(draft_text, p.phrase)}) for p in phrases
    ]
