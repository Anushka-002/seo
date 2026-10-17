"""Dashboard statistics for the calling browser's own analyses."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.analyses import get_owner
from app.core.db import get_db
from app.models import Analysis
from app.schemas.dashboard import DashboardStats
from app.services import dashboard as agg

router = APIRouter(tags=["dashboard"])
WINDOW = 500  # most recent runs used for trend and keyword charts
GAP_SAMPLE = 50  # most recent runs whose result payloads are scanned for common gaps


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(
    owner: str = Depends(get_owner), db: Session = Depends(get_db)
) -> DashboardStats:
    """Totals, score trend, top keywords and the most common content gaps."""
    mine = [Analysis.owner == owner, Analysis.is_demo.is_(False), Analysis.status == "done"]
    total, avg, best = db.execute(
        select(func.count(), func.avg(Analysis.score), func.max(Analysis.score)).where(*mine)
    ).one()
    recent = db.execute(
        select(Analysis.id, Analysis.keyword, Analysis.score, Analysis.created_at)
        .where(*mine)
        .order_by(Analysis.created_at.desc())
        .limit(WINDOW)
    ).all()
    trend = agg.score_trend(recent)
    newest_results = (
        select(Analysis.result)
        .where(*mine)
        .order_by(Analysis.created_at.desc())
        .limit(GAP_SAMPLE)
    )
    gaps, sample = agg.common_gaps(db.scalars(newest_results))
    return DashboardStats(
        total_analyses=total,
        avg_score=round(float(avg), 1) if avg is not None else None,
        best_score=round(float(best), 1) if best is not None else None,
        latest_score=trend[-1]["score"] if trend else None,
        score_change=round(trend[-1]["score"] - trend[0]["score"], 1) if len(trend) > 1 else None,
        score_trend=trend,
        top_keywords=agg.top_keywords(recent),
        common_gaps=gaps,
        gap_sample_size=sample,
    )
