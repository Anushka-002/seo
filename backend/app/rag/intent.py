"""Rule-based search-intent classification for SERPs and drafts."""

from pydantic import BaseModel

from app.rag.draft import Draft
from app.rag.text_utils import first_words, tokenize
from app.services.serp import SerpData

INTENTS = ("informational", "commercial", "transactional", "navigational")

# Single-word cues (matched on tokens) and multi-word cues (matched on the joined text).
CUES: dict[str, tuple[set[str], tuple[str, ...]]] = {
    "informational": (
        {"how", "what", "why", "guide", "tutorial", "tips", "ideas", "examples", "meaning",
         "definition", "explained", "learn", "basics", "beginner", "beginners", "steps",
         "checklist"},
        ("how to", "what is", "step by step", "things to know"),
    ),
    "commercial": (
        {"best", "top", "review", "reviews", "vs", "versus", "compare", "comparison",
         "alternatives", "alternative", "ranked", "recommended", "pros", "cons", "worth"},
        ("buyer's guide", "buying guide", "which is better"),
    ),
    "transactional": (
        {"buy", "price", "prices", "pricing", "discount", "deal", "deals", "coupon", "order",
         "shop", "cheap", "sale", "purchase", "free", "shipping", "download", "trial"},
        ("add to cart", "for sale", "near me"),
    ),
    "navigational": (
        {"login", "signin", "official", "homepage", "website", "portal", "app"},
        ("sign in", "log in", "customer service", "contact us"),
    ),
}  # fmt: skip


class IntentResult(BaseModel):
    """Intent distribution with the dominant intent."""

    primary: str
    scores: dict[str, float]  # normalised to sum to 1
    confidence: float  # share of the primary intent
    cues: list[str] = []  # strongest cue words found (for explanations)


def _hits(text: str) -> tuple[dict[str, float], dict[str, int]]:
    tokens = tokenize(text)
    joined = " ".join(tokens)
    counts = {i: 0.0 for i in INTENTS}
    found: dict[str, int] = {}
    token_set_counts: dict[str, int] = {}
    for t in tokens:
        token_set_counts[t] = token_set_counts.get(t, 0) + 1
    for intent, (words, phrases) in CUES.items():
        for w in words:
            c = token_set_counts.get(w, 0)
            if c:
                counts[intent] += c
                found[w] = found.get(w, 0) + c
        for ph in phrases:
            c = joined.count(ph.replace("'", ""))
            if c:
                counts[intent] += 2 * c
                found[ph] = found.get(ph, 0) + c
    return counts, found


def _finish(weighted: dict[str, float], found: dict[str, int]) -> IntentResult:
    total = sum(weighted.values())
    if total == 0:
        scores = {i: (1.0 if i == "informational" else 0.0) for i in INTENTS}
        return IntentResult(primary="informational", scores=scores, confidence=0.0, cues=[])
    scores = {i: weighted[i] / total for i in INTENTS}
    primary = max(INTENTS, key=lambda i: (scores[i], -INTENTS.index(i)))
    cues = [w for w, _ in sorted(found.items(), key=lambda kv: -kv[1])[:6]]
    return IntentResult(primary=primary, scores=scores, confidence=scores[primary], cues=cues)


def classify_serp_intent(keyword: str, serp: SerpData) -> IntentResult:
    """Intent of a keyword from the query itself (x3), result titles (x1) and snippets (x0.5)."""
    weighted = {i: 0.0 for i in INTENTS}
    found: dict[str, int] = {}
    parts = [(keyword, 3.0)]
    parts += [(r.title, 1.0) for r in serp.results] + [(r.snippet, 0.5) for r in serp.results]
    for text, weight in parts:
        counts, f = _hits(text)
        for i in INTENTS:
            weighted[i] += weight * counts[i]
        for w, c in f.items():
            found[w] = found.get(w, 0) + c
    if serp.people_also_ask:  # questions strongly signal informational intent
        weighted["informational"] += 0.5 * len(serp.people_also_ask)
    return _finish(weighted, found)


def classify_draft_intent(draft: Draft) -> IntentResult:
    """Intent of a draft from its title/H1/headings (x2) and opening 150 words (x1)."""
    weighted = {i: 0.0 for i in INTENTS}
    found: dict[str, int] = {}
    prominent = " ".join([draft.title or "", draft.h1 or "", *[h.text for h in draft.headings]])
    for text, weight in ((prominent, 2.0), (first_words(draft.text, 150), 1.0)):
        counts, f = _hits(text)
        for i in INTENTS:
            weighted[i] += weight * counts[i]
        for w, c in f.items():
            found[w] = found.get(w, 0) + c
    return _finish(weighted, found)


def intent_match(serp: IntentResult, draft: IntentResult) -> float:
    """0..1: 60% same primary intent, 40% distribution overlap."""
    overlap = sum(min(serp.scores[i], draft.scores[i]) for i in INTENTS)
    same = 1.0 if serp.primary == draft.primary else 0.0
    return 0.6 * same + 0.4 * overlap
