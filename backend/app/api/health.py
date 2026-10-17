"""Health-check endpoint."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.analysis import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report liveness and which providers are configured (never exposes keys)."""
    s = get_settings()
    return HealthResponse(
        status="ok",
        app=s.app_name,
        version=s.version,
        llm_provider=s.llm_provider,
        serp_provider="serper" if s.use_serper else "duckduckgo",
    )
