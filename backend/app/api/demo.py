"""Demo endpoint: a saved real analysis that works without any API quota."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.analysis import AnalyzeAccepted
from app.services.demo import DemoUnavailableError, ensure_demo

router = APIRouter(tags=["demo"])


@router.post("/demo", response_model=AnalyzeAccepted)
def start_demo(db: Session = Depends(get_db)) -> AnalyzeAccepted:
    """Return the id of the shared, finished demo analysis (no rate limit, no pipeline run)."""
    try:
        row = ensure_demo(db)
    except DemoUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    return AnalyzeAccepted(
        analysis_id=row.id, status="done", events_url=f"/api/analyses/{row.id}/events"
    )
