"""Pydantic schemas for the analysis API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

MIN_WORDS, MAX_WORDS = 100, 20_000

Status = Literal["pending", "running", "done", "failed"]


class AnalyzeRequest(BaseModel):
    """Input for POST /api/analyze: a keyword plus exactly one draft source."""

    keyword: str = Field(min_length=2, max_length=100)
    draft_text: str | None = None
    draft_url: HttpUrl | None = None
    # Optional on-page elements for pasted drafts (used by the keyword-placement score).
    draft_title: str | None = Field(default=None, max_length=200)
    meta_description: str | None = Field(default=None, max_length=400)
    country: str = Field(default="us", min_length=2, max_length=8)

    @model_validator(mode="after")
    def _validate_draft(self) -> "AnalyzeRequest":
        self.keyword = " ".join(self.keyword.split())
        if len(self.keyword) < 2:
            raise ValueError("keyword must contain at least 2 characters")
        if bool(self.draft_text) == bool(self.draft_url):
            raise ValueError("provide exactly one of draft_text or draft_url")
        if self.draft_text:
            words = len(self.draft_text.split())
            if not MIN_WORDS <= words <= MAX_WORDS:
                raise ValueError(f"draft_text must be {MIN_WORDS}-{MAX_WORDS} words (got {words})")
        return self


class ScoreComponent(BaseModel):
    """One weighted component of the SEO score."""

    name: str
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    reason: str


class AnalysisSummary(BaseModel):
    """Compact row for history lists."""

    model_config = {"from_attributes": True}

    id: str
    keyword: str
    status: Status
    score: float | None
    is_demo: bool
    created_at: datetime


class AnalysisDetail(AnalysisSummary):
    """Full analysis including the result payload."""

    country: str
    stage: str | None
    result: dict | None
    error: str | None


class AnalyzeAccepted(BaseModel):
    """202 response: poll GET /api/analyses/{id} or stream .../events."""

    analysis_id: str
    status: Status
    events_url: str


class AnalysisPage(BaseModel):
    """Paginated history."""

    items: list[AnalysisSummary]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    """GET /api/health payload."""

    status: Literal["ok"]
    app: str
    version: str
    llm_provider: str
    serp_provider: Literal["serper", "duckduckgo"]
