"""Analysis endpoints: create, stream progress (SSE), list, read, delete."""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Analysis
from app.schemas.analysis import (
    AnalysisDetail,
    AnalysisPage,
    AnalysisSummary,
    AnalyzeAccepted,
    AnalyzeRequest,
)
from app.services.netguard import BlockedHostError, check_url_shape, ensure_public_host
from app.services.pipeline import Runtime, start_analysis
from app.services.progress import ProgressEvent
from app.services.ratelimit import RateLimiter, client_ip, hash_ip

log = logging.getLogger(__name__)
router = APIRouter(tags=["analyses"])
HEARTBEAT_SECONDS = 15.0
_CLIENT_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_limiter(request: Request) -> RateLimiter:
    return request.app.state.limiter


def get_owner(x_client_id: str = Header(default="")) -> str:
    """Anonymous per-browser identity. Only its hash is stored; it scopes history visibility."""
    if not _CLIENT_ID.match(x_client_id):
        raise HTTPException(
            400, "Missing or invalid X-Client-Id header (16-64 chars: A-Z a-z 0-9 _ -)."
        )
    return hash_ip("client:" + x_client_id)


def _visible(row: Analysis | None, owner: str) -> Analysis:
    if row is None or not (row.owner == owner or row.is_demo):
        raise HTTPException(404, "Analysis not found.")
    return row


@router.post("/analyze", response_model=AnalyzeAccepted, status_code=202)
async def create_analysis(
    body: AnalyzeRequest,
    request: Request,
    response: Response,
    owner: str = Depends(get_owner),
    rt: Runtime = Depends(get_runtime),
    limiter: RateLimiter = Depends(get_limiter),
    db: Session = Depends(get_db),
) -> AnalyzeAccepted:
    """Validate, rate-limit, store, and start the analysis in the background."""
    ip = client_ip(request, rt.settings.trusted_proxy_hops)
    allowed, retry_after = limiter.check(ip)
    if not allowed:
        raise HTTPException(
            429,
            f"Rate limit reached ({limiter.limit} analyses per hour). Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    if body.draft_url and rt.settings.block_private_hosts:  # fail fast; the pipeline re-checks
        try:
            check_url_shape(str(body.draft_url))
            await ensure_public_host(urlparse(str(body.draft_url)).hostname or "")
        except BlockedHostError as exc:
            raise HTTPException(400, str(exc)) from exc
    row = Analysis(
        keyword=body.keyword, country=body.country.lower(), draft_text=body.draft_text,
        draft_url=str(body.draft_url) if body.draft_url else None, draft_title=body.draft_title,
        meta_description=body.meta_description, status="pending", stage="queued",
        client_ip=hash_ip(ip), owner=owner,
    )  # fmt: skip
    db.add(row)
    db.commit()
    rt.broker.publish(row.id, "queued", "Queued", 2)
    start_analysis(row.id, rt)
    return AnalyzeAccepted(
        analysis_id=row.id, status="pending", events_url=f"/api/analyses/{row.id}/events"
    )


def _sse(event: ProgressEvent) -> str:
    name = "progress" if event.status == "running" else event.status
    return f"id: {event.seq}\nevent: {name}\ndata: {json.dumps(event.to_dict())}\n\n"


async def _stream(analysis_id: str, rt: Runtime, row: Analysis) -> AsyncIterator[str]:
    """SSE body: replay + live events, 15s heartbeats, and a synthetic final event for old runs."""
    if not rt.broker.is_known(analysis_id):
        if row.status == "done":
            yield _sse(ProgressEvent(analysis_id, "done", "done", "Analysis complete", 100,
                                     data={"score": row.score}))  # fmt: skip
        elif row.status == "failed":
            yield _sse(ProgressEvent(analysis_id, "error", "error", row.error or "Failed", 0))
        return
    agen = rt.broker.subscribe(analysis_id).__aiter__()
    pending: asyncio.Future | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(agen.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=HEARTBEAT_SECONDS)
            if not done:
                yield ": keep-alive\n\n"
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            yield _sse(event)
    finally:  # client disconnected or stream finished
        if pending is not None and not pending.done():
            pending.cancel()
        await agen.aclose()


@router.get("/analyses/{analysis_id}/events")
async def stream_events(
    analysis_id: str,
    owner: str = Depends(get_owner),
    rt: Runtime = Depends(get_runtime),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Server-Sent Events: queued, searching, scraping, indexing, analyzing, generating, done."""
    row = _visible(db.get(Analysis, analysis_id), owner)
    return StreamingResponse(
        _stream(analysis_id, rt, row),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/analyses", response_model=AnalysisPage)
def list_analyses(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=100),
    sort: Literal["created_at", "score", "keyword"] = Query("created_at"),
    order: Literal["asc", "desc"] = Query("desc"),
    owner: str = Depends(get_owner),
    db: Session = Depends(get_db),
) -> AnalysisPage:
    """The caller's analyses (newest first by default), filterable by keyword and sortable."""
    cond = [Analysis.owner == owner, Analysis.is_demo.is_(False)]
    if q:
        cond.append(Analysis.keyword.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(Analysis).where(*cond)) or 0
    column = {
        "created_at": Analysis.created_at,
        "score": Analysis.score,
        "keyword": Analysis.keyword,
    }[sort]
    direction = column.asc() if order == "asc" else column.desc()
    rows = db.scalars(
        select(Analysis)
        .where(*cond)
        .order_by(direction, Analysis.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AnalysisPage(
        items=[AnalysisSummary.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/analyses/{analysis_id}", response_model=AnalysisDetail)
def get_analysis(
    analysis_id: str, owner: str = Depends(get_owner), db: Session = Depends(get_db)
) -> AnalysisDetail:
    return AnalysisDetail.model_validate(_visible(db.get(Analysis, analysis_id), owner))


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(
    analysis_id: str, owner: str = Depends(get_owner), db: Session = Depends(get_db)
) -> Response:
    row = db.get(Analysis, analysis_id)
    if row is None or row.owner != owner:  # demo rows and others' rows cannot be deleted
        raise HTTPException(404, "Analysis not found.")
    db.delete(row)
    db.commit()
    return Response(status_code=204)
