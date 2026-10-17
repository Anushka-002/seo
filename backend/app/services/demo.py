"""The bundled demo analysis, so the public demo works even with no API quota."""

import json
import logging
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Analysis
from app.schemas.result import AnalysisResult

log = logging.getLogger(__name__)

DEMO_ID = "demo-best-running-shoes"
DEMO_FILE = Path(__file__).resolve().parent.parent / "data" / "demo_analysis.json"


class DemoUnavailableError(RuntimeError):
    """The demo file is missing or no longer matches the result schema."""


@lru_cache
def load_demo_result() -> AnalysisResult:
    """Read and validate the saved analysis (regenerate it with scripts/build_demo.py)."""
    try:
        return AnalysisResult.model_validate(json.loads(DEMO_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:  # pydantic's ValidationError is a ValueError
        log.error("demo analysis unusable: %s", exc)
        raise DemoUnavailableError("The demo analysis is not available.") from exc


def ensure_demo(db: Session) -> Analysis:
    """Create or refresh the shared demo row (is_demo=True, readable by everyone)."""
    result = load_demo_result()
    payload = result.model_dump(mode="json")
    row = db.get(Analysis, DEMO_ID)
    if row is None:
        row = Analysis(id=DEMO_ID, keyword=result.keyword, country="us", is_demo=True)
        db.add(row)
    elif row.result == payload and row.status == "done":
        return row
    row.keyword, row.status, row.stage = result.keyword, "done", "done"
    row.score, row.result, row.error = result.score, payload, None
    row.is_demo, row.owner = True, None
    row.created_at = datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError:  # two first visitors raced to insert the row; theirs is identical
        db.rollback()
        existing = db.get(Analysis, DEMO_ID)
        if existing is None:
            raise
        return existing
    return row
