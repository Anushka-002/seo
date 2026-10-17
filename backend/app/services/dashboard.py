"""Pure aggregation helpers behind the dashboard (no DB or web imports, easy to test)."""

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any, Protocol


class ScoredRun(Protocol):
    """Anything shaped like a finished Analysis row (only these columns are read)."""

    id: str
    keyword: str
    score: float | None
    created_at: Any


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def score_trend(rows: Sequence[ScoredRun], limit: int = 30) -> list[dict[str, Any]]:
    """The `limit` most recent scored runs, oldest first, as chart points."""
    scored = [r for r in rows if r.score is not None]
    scored.sort(key=lambda r: r.created_at)
    return [
        {"id": r.id, "keyword": r.keyword, "score": round(float(r.score), 1),
         "created_at": r.created_at}
        for r in scored[-limit:]
    ]  # fmt: skip


def top_keywords(rows: Iterable[ScoredRun], limit: int = 8) -> list[dict[str, Any]]:
    """Most-analysed keywords (case/whitespace-insensitive) with their average score."""
    groups: dict[str, list[ScoredRun]] = {}
    for r in rows:
        if r.score is None:
            continue
        groups.setdefault(_norm(r.keyword), []).append(r)
    out = []
    for runs in groups.values():
        latest = max(runs, key=lambda r: r.created_at)  # display the most recent spelling
        out.append({
            "keyword": latest.keyword,
            "count": len(runs),
            "avg_score": round(sum(float(r.score) for r in runs) / len(runs), 1),
        })  # fmt: skip
    out.sort(key=lambda d: (-d["count"], -d["avg_score"], d["keyword"].lower()))
    return out[:limit]


def common_gaps(results: Iterable[dict | None], limit: int = 8) -> tuple[list[dict], int]:
    """Gap topics ranked by how many analyses contain them.

    Returns (stats, sample_size). A topic counts once per analysis even when it appears twice.
    """
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    sample = 0
    for result in results:
        if not result:
            continue
        sample += 1
        seen: set[str] = set()
        for topic in result.get("topics", []):
            label = str(topic.get("label", "")).strip()
            key = _norm(label)
            if topic.get("is_gap") and key and key not in seen:
                seen.add(key)
                display.setdefault(key, label)
        counts.update(seen)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    stats = [
        {"label": display[key], "count": n, "share": round(n / sample, 3)} for key, n in ranked
    ]
    return stats, sample
