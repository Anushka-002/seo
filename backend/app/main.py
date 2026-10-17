"""FastAPI application entrypoint."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from app.api import analyses, dashboard, demo, health
from app.core.config import get_settings
from app.core.db import SessionLocal, init_db
from app.core.logging import configure_logging
from app.models import Analysis
from app.rag.embeddings import get_embedder
from app.services.pipeline import Runtime
from app.services.ratelimit import RateLimiter

log = logging.getLogger("seoul")


def _mark_interrupted() -> int:
    """Runs left 'pending/running' by a previous process can never finish: fail them."""
    with SessionLocal() as db:
        res = db.execute(
            update(Analysis)
            .where(Analysis.status.in_(["pending", "running"]))
            .values(
                status="failed", error="The server restarted during this analysis. Run it again."
            )
        )
        db.commit()
        return res.rowcount or 0


async def _warm_embedder() -> None:
    """Load the embedding model at startup so the first analysis is not slow."""
    try:
        await asyncio.to_thread(get_embedder)
        log.info("embedder ready")
    except Exception:
        log.exception("embedder warm-up failed (will retry on first analysis)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configure logging, create tables, and build the process-wide runtime."""
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db()
    interrupted = _mark_interrupted()
    app.state.runtime = Runtime(settings=settings)
    app.state.limiter = RateLimiter(settings.rate_limit_per_hour)
    warm = asyncio.create_task(_warm_embedder()) if settings.embedder == "sbert" else None
    fields = {"version": settings.version, "interrupted_runs": interrupted}
    log.info("startup complete", extra={"extra_fields": fields})
    yield
    for task in [*app.state.runtime.tasks, *([warm] if warm else [])]:
        task.cancel()


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="SEO Content Optimizer Agent powered by RAG over top-ranking pages.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(analyses.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(demo.router, prefix="/api")
    return app


app = create_app()
