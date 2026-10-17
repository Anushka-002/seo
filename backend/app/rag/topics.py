"""Competitor subtopic discovery (KMeans on chunk embeddings) and draft coverage."""

import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from app.rag.chunking import Chunk
from app.rag.text_utils import STOPWORDS, stem, tokenize

K_MIN, K_MAX = 4, 10
# Heuristic thresholds (draft similarity / what competitor pages score against each other).
# Chosen conservatively so a draft with a dedicated section is not told to add it again;
# tune against real SERPs + the real embedding model (see docs/evaluation.md in Phase 8).
GAP_RATIO = 0.70  # below 70% of the competitor reference = gap
FULL_RATIO = 0.92  # >= 92% counts as fully covered
EMPTY_RATIO = 0.45  # <= 45% counts as not covered at all
INTRO_SHARE = 0.6  # clusters that are >= 60% intro text are ignored
MIN_PAGE_SHARE = 0.3  # a subtopic must appear on >= 30% of pages (and >= 2) to matter


@dataclass
class TopicCluster:
    """A group of similar competitor chunks = one subtopic."""

    id: int
    chunk_idx: list[int]
    centroid: np.ndarray
    label: str = ""
    label_source: str = "terms"
    pages: set[str] = field(default_factory=set)
    page_share: float = 0.0
    reference_sim: float = 0.0  # median over pages of best chunk-to-centroid similarity
    top_terms: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)

    @property
    def severity(self) -> str:
        if self.page_share >= 0.6:
            return "high"
        return "medium" if self.page_share >= 0.4 else "low"


def choose_k(matrix: np.ndarray) -> tuple[int, np.ndarray]:
    """Pick k in [4, 10] by silhouette (cosine); returns (k, labels). Deterministic."""
    n = len(matrix)
    k_max = min(K_MAX, n - 1)
    if k_max < 2:
        return 1, np.zeros(n, dtype=int)
    best: tuple[float, int, np.ndarray] | None = None
    for k in range(min(K_MIN, k_max), k_max + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(matrix)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(matrix, labels, metric="cosine")
        if best is None or score > best[0] + 1e-9:
            best = (score, k, labels)
    if best is None:
        return 1, np.zeros(n, dtype=int)
    return best[1], best[2]


def _normalise(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v / norm if norm else v


def _top_terms(texts: list[str], keyword_stems: set[str], n: int = 4) -> list[str]:
    """Most frequent non-stopword stems in a cluster (excluding the target keyword's words)."""
    counts: Counter[str] = Counter()
    for t in texts:
        counts.update(
            s
            for s in (stem(w) for w in tokenize(t))
            if s not in STOPWORDS and len(s) > 3 and s not in keyword_stems
        )
    return [w for w, _ in counts.most_common(n)]


def _reference_similarity(
    chunks: list[Chunk], matrix: np.ndarray, idx: list[int], centroid: np.ndarray
) -> float:
    """What a competitor page typically scores against the rest of the cluster.

    Leave-one-out: each page's best chunk is compared with a centroid built WITHOUT that page,
    the same situation as an outside draft. Using the full centroid would let every competitor
    match itself and make the draft look worse than it is. With < 3 pages we fall back to the
    inclusive centroid.
    """
    by_page: dict[str, list[int]] = {}
    for i in idx:
        by_page.setdefault(chunks[i].source_url, []).append(i)
    sims = []
    for url, own in by_page.items():
        others = [i for i in idx if chunks[i].source_url != url]
        c = _normalise(matrix[others].mean(axis=0)) if len(by_page) >= 3 and others else centroid
        sims.append(float((matrix[own] @ c).max()))
    return float(np.median(sims))


def discover_topics(
    chunks: list[Chunk], matrix: np.ndarray, keyword: str, n_pages: int
) -> list[TopicCluster]:
    """Cluster competitor chunks; keep subtopics that several pages agree on."""
    if len(chunks) < 2:
        return []
    k, labels = choose_k(matrix)
    kw_stems = {stem(t) for t in tokenize(keyword)}
    need = max(2, math.ceil(MIN_PAGE_SHARE * n_pages))
    clusters: list[TopicCluster] = []
    for cid in sorted(set(labels.tolist())):
        idx = [i for i, lab in enumerate(labels) if lab == cid]
        centroid = _normalise(matrix[idx].mean(axis=0))
        pages = {chunks[i].source_url for i in idx}
        if len(pages) < need:
            continue  # idiosyncratic to a page or two: not a competitor consensus topic
        if sum(chunks[i].is_intro for i in idx) >= INTRO_SHARE * len(idx):
            continue  # generic page intros are framing, not a subtopic to cover
        sims = matrix[idx] @ centroid
        order = [idx[j] for j in np.argsort(-sims)]
        reference = _reference_similarity(chunks, matrix, idx, centroid)
        head_counts = Counter(
            chunks[i].heading for i in idx if chunks[i].heading and not chunks[i].is_intro
        )
        headings = [h for h, _ in head_counts.most_common(3)]
        terms = _top_terms([chunks[i].text for i in idx], kw_stems)
        if headings:
            label, source = headings[0], "heading"
        else:
            label, source = (", ".join(terms[:3]) or f"topic {cid + 1}"), "terms"
        clusters.append(
            TopicCluster(
                id=len(clusters), chunk_idx=idx, centroid=centroid, label=label,
                label_source=source, pages=pages, page_share=len(pages) / n_pages,
                reference_sim=reference, top_terms=terms,
                headings=headings, evidence_ids=[chunks[i].id for i in order[:3]],
            )
        )  # fmt: skip
    clusters.sort(key=lambda c: (-c.page_share, c.label))
    for new_id, c in enumerate(clusters):
        c.id = new_id
    return clusters


def coverage_from_ratio(ratio: float) -> float:
    """Map draft/reference similarity ratio to 0..1 coverage (linear between thresholds)."""
    if ratio >= FULL_RATIO:
        return 1.0
    if ratio <= EMPTY_RATIO:
        return 0.0
    return (ratio - EMPTY_RATIO) / (FULL_RATIO - EMPTY_RATIO)


def measure_coverage(
    clusters: list[TopicCluster], draft_matrix: np.ndarray
) -> list[tuple[float, float, bool]]:
    """For each cluster: (draft_similarity, coverage 0..1, is_gap)."""
    out = []
    for c in clusters:
        sim = float((draft_matrix @ c.centroid).max()) if len(draft_matrix) else 0.0
        ratio = sim / c.reference_sim if c.reference_sim > 0 else 0.0
        out.append((sim, coverage_from_ratio(ratio), ratio < GAP_RATIO))
    return out
