"""Deterministic draft analysis against the competitor RAG index (Phase 3)."""

import numpy as np

from app.rag.chunking import Chunk, chunk_text
from app.rag.draft import Draft
from app.rag.index import RagIndex
from app.rag.intent import classify_draft_intent, classify_serp_intent, intent_match
from app.rag.keyphrases import extract_competitor_keyphrases, mark_draft_coverage
from app.rag.scoring import (
    check_placement,
    score_intent,
    score_keyword_coverage,
    score_placement,
    score_readability,
    score_structure,
    score_topic_coverage,
    structure_metrics,
    total_score,
)
from app.rag.topics import discover_topics, measure_coverage
from app.schemas.result import AnalysisResult, CompetitorSummary, TopicGap
from app.services.scraper import ScrapedPage
from app.services.serp import SerpData

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def chunk_draft(draft: Draft) -> list[Chunk]:
    """Chunk the draft section by section, same settings as the competitor pages."""
    chunks: list[Chunk] = []
    for heading, body in draft.sections:
        chunks.extend(
            chunk_text(body, source_url="draft", rank=0, heading=heading, start_index=len(chunks))
        )
    return chunks


def embed_draft(draft: Draft, index: RagIndex) -> np.ndarray:
    """(n_draft_chunks, dim) embeddings using the same model as the index."""
    chunks = chunk_draft(draft)
    if not chunks:
        return np.zeros((0, index.embedder.dim), dtype=np.float32)
    return index.embedder.embed([c.embed_text for c in chunks])


def analyze_draft(
    *,
    keyword: str,
    draft: Draft,
    pages: list[ScrapedPage],
    serp: SerpData,
    index: RagIndex,
) -> AnalysisResult:
    """Score a draft against competitors. LLM-free, deterministic."""
    clusters = discover_topics(index.chunks, index.matrix, keyword, len(pages))
    coverages = measure_coverage(clusters, embed_draft(draft, index))

    phrases = mark_draft_coverage(extract_competitor_keyphrases(pages, keyword), draft.text)
    placement = check_placement(keyword, draft)
    metrics = structure_metrics(draft, pages)
    serp_intent = classify_serp_intent(keyword, serp)
    draft_intent = classify_draft_intent(draft)
    match = intent_match(serp_intent, draft_intent)

    components = [
        score_topic_coverage(clusters, coverages),
        score_keyword_coverage(phrases),
        score_placement(placement),
        score_structure(metrics),
        score_intent(match, serp_intent, draft_intent),
        score_readability(metrics),
    ]
    topics = [
        TopicGap(
            cluster_id=c.id, label=c.label, label_source=c.label_source,
            page_count=len(c.pages), page_share=round(c.page_share, 3),
            coverage=round(cov, 3), is_gap=gap, severity=c.severity,
            draft_similarity=round(sim, 3), reference_similarity=round(c.reference_sim, 3),
            example_headings=c.headings, top_terms=c.top_terms,
            evidence_chunk_ids=c.evidence_ids,
        )
        for c, (sim, cov, gap) in zip(clusters, coverages, strict=True)
    ]  # fmt: skip
    topics.sort(key=lambda t: (not t.is_gap, _SEVERITY_ORDER[t.severity], -t.page_share, t.label))
    return AnalysisResult(
        keyword=keyword,
        draft_title=draft.title,
        draft_meta_description=draft.meta_description,
        score=total_score(components),
        components=components,
        topics=topics,
        keyphrases=sorted(phrases, key=lambda p: (p.in_draft, -p.page_share, p.phrase)),
        placement=placement,
        structure=metrics,
        serp_intent=serp_intent,
        draft_intent=draft_intent,
        intent_match=round(match, 3),
        competitors=[
            CompetitorSummary(
                rank=p.rank,
                url=p.url,
                title=p.title,
                word_count=p.word_count,
                headings=len(p.headings),
            )
            for p in pages
        ],  # fmt: skip
        embedder=index.embedder.name,
        n_clusters=len(clusters),
    )
