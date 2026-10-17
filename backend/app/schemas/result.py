"""Structured analysis result stored in Analysis.result and returned by the API."""

from pydantic import BaseModel, Field

from app.rag.intent import IntentResult
from app.rag.keyphrases import Keyphrase
from app.schemas.analysis import ScoreComponent


class TopicGap(BaseModel):
    """A subtopic competitors cover, with how well the draft covers it."""

    cluster_id: int
    label: str
    label_source: str  # heading | terms | llm
    page_count: int
    page_share: float
    coverage: float = Field(ge=0, le=1)
    is_gap: bool
    severity: str  # high | medium | low
    draft_similarity: float
    reference_similarity: float
    example_headings: list[str] = []
    top_terms: list[str] = []
    evidence_chunk_ids: list[str] = []  # nearest competitor chunks (used for RAG in Phase 4)


class StructureMetrics(BaseModel):
    """Draft vs competitor medians."""

    draft_words: int
    median_competitor_words: int
    draft_headings: int
    median_competitor_headings: int
    draft_readability: float  # Flesch reading ease
    median_competitor_readability: float


class PlacementCheck(BaseModel):
    """Whether the target keyword appears in a key on-page element."""

    element: str
    available: bool
    status: str  # exact | partial | missing | not_provided


class CompetitorSummary(BaseModel):
    """One row of the competitor comparison table."""

    rank: int
    url: str
    title: str
    word_count: int
    headings: int


class Source(BaseModel):
    """A competitor page cited as [n] in recommendations."""

    n: int
    url: str
    title: str
    rank: int


class Evidence(BaseModel):
    """A retrieved competitor passage backing a recommendation."""

    source_n: int
    chunk_id: str
    heading: str
    excerpt: str


class GapRecommendation(BaseModel):
    """What to add to the draft for one content gap, grounded in retrieved passages."""

    cluster_id: int
    label: str
    severity: str
    heading_suggestion: str
    recommendation: str
    citations: list[int]
    evidence: list[Evidence]
    generated_by: str  # llm | template
    model_cited: bool  # True when the model's own [n] markers were valid


class OutlineItem(BaseModel):
    """One heading in the suggested outline."""

    level: int = Field(ge=2, le=3)
    heading: str = Field(min_length=2, max_length=120)
    notes: str = Field(default="", max_length=300)


class SeoSuggestions(BaseModel):
    """Rewritten on-page elements."""

    title: str = Field(max_length=60)
    meta_description: str = Field(max_length=155)
    outline: list[OutlineItem]
    title_has_keyword: bool
    meta_has_keyword: bool


class AnalysisResult(BaseModel):
    """Everything computed deterministically in Phase 3."""

    keyword: str
    draft_title: str | None = None  # the draft's own title / meta (for before-vs-after display)
    draft_meta_description: str | None = None
    score: float = Field(ge=0, le=100)
    components: list[ScoreComponent]
    topics: list[TopicGap]
    keyphrases: list[Keyphrase]
    placement: list[PlacementCheck]
    structure: StructureMetrics
    serp_intent: IntentResult
    draft_intent: IntentResult
    intent_match: float
    competitors: list[CompetitorSummary]
    embedder: str
    n_clusters: int
    sources: list[Source] = []
    recommendations: list[GapRecommendation] = []
    suggestions: SeoSuggestions | None = None
    llm_status: str = "skipped"  # ok | partial | skipped | failed
    llm_message: str = ""
