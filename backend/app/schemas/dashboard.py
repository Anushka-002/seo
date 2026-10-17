"""Schemas for GET /api/dashboard/stats."""

from datetime import datetime

from pydantic import BaseModel, Field


class TrendPoint(BaseModel):
    """One finished analysis on the score-over-time chart."""

    id: str
    keyword: str
    score: float
    created_at: datetime


class KeywordStat(BaseModel):
    """How often a keyword was analysed and its average score."""

    keyword: str
    count: int = Field(ge=1)
    avg_score: float


class GapStat(BaseModel):
    """A content-gap topic that keeps showing up across analyses."""

    label: str
    count: int = Field(ge=1)
    share: float = Field(ge=0, le=1)  # fraction of the sampled analyses that had this gap


class DashboardStats(BaseModel):
    """Everything the dashboard needs, scoped to the calling browser."""

    total_analyses: int
    avg_score: float | None
    best_score: float | None
    latest_score: float | None
    score_change: float | None  # last minus first point of `score_trend`; None with < 2 points
    score_trend: list[TrendPoint]  # oldest -> newest
    top_keywords: list[KeywordStat]
    common_gaps: list[GapStat]
    gap_sample_size: int  # analyses the `common_gaps` shares are based on
