"""The analysis pipeline as a LangGraph graph, plus the runtime that executes it."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, TypedDict
from urllib.parse import urlparse

import httpx
import trafilatura
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.models import Analysis
from app.rag.analyzer import analyze_draft
from app.rag.draft import Draft, draft_from_page, parse_draft_text
from app.rag.embeddings import Embedder, get_embedder
from app.rag.index import RagIndex
from app.schemas.analysis import MIN_WORDS
from app.schemas.result import AnalysisResult
from app.services.cache import get_cached, set_cached
from app.services.ingest import build_index
from app.services.llm import LLMClient, LLMConfigError, get_llm
from app.services.netguard import (
    BlockedHostError,
    check_url_shape,
    ensure_public_host,
    guarded_client,
)
from app.services.progress import ProgressBroker
from app.services.progress import broker as default_broker
from app.services.recommend import generate_recommendations
from app.services.scraper import ScrapedPage, ScrapeError, extract_page, scrape_pages
from app.services.serp import SerpData, SerpError, fetch_serp

log = logging.getLogger(__name__)

STAGES = {  # stage -> progress % when it starts
    "queued": 2, "searching": 10, "scraping": 25, "indexing": 50, "analyzing": 65,
    "generating": 80, "done": 100,
}  # fmt: skip
USER_ERRORS = (SerpError, ScrapeError, BlockedHostError)


class DraftError(ValueError):
    """The user's draft (text or URL) could not be used."""


class PipelineState(TypedDict, total=False):
    analysis_id: str
    keyword: str
    country: str
    draft_text: str | None
    draft_url: str | None
    draft_title: str | None
    meta_description: str | None
    draft: Draft
    serp: SerpData
    pages: list[ScrapedPage]
    result: AnalysisResult


@dataclass
class Runtime:
    """Process-wide dependencies. Tests override http / llm / embedder."""

    settings: Settings = field(default_factory=get_settings)
    session_factory: sessionmaker[Session] = SessionLocal
    broker: ProgressBroker = default_broker
    http: httpx.AsyncClient | None = None
    llm: LLMClient | None = None
    embedder: Embedder | None = None
    semaphore: asyncio.Semaphore | None = None
    tasks: set[asyncio.Task] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.semaphore is None:
            self.semaphore = asyncio.Semaphore(self.settings.max_concurrent_analyses)


@dataclass
class RunContext:
    """Per-run handles that are not part of the serialisable graph state."""

    rt: Runtime
    index: RagIndex | None = None


# ------------------------------------------------------------------ helpers
def _emit(ctx: RunContext, state: PipelineState, stage: str, message: str, pct: int | None = None):
    aid = state["analysis_id"]
    ctx.rt.broker.publish(aid, stage, message, STAGES.get(stage, 0) if pct is None else pct)
    with ctx.rt.session_factory() as db:
        row = db.get(Analysis, aid)
        if row is not None:
            row.status, row.stage = "running", stage
            db.commit()


def _norm_url(url: str) -> str:
    p = urlparse(url)
    return f"{(p.hostname or '').removeprefix('www.')}{p.path.rstrip('/')}".lower()


async def load_draft(state: PipelineState, rt: Runtime) -> Draft:
    """Pasted text is parsed directly; a URL is fetched through the SSRF guard."""
    if state.get("draft_text"):
        return parse_draft_text(
            state["draft_text"],
            title=state.get("draft_title"),
            meta_description=state.get("meta_description"),
        )
    url = state["draft_url"]
    s = rt.settings
    if s.block_private_hosts:
        check_url_shape(url)
        await ensure_public_host(urlparse(url).hostname or "")
    client = rt.http or guarded_client(
        enabled=s.block_private_hosts, headers={"User-Agent": s.user_agent}
    )
    try:
        resp = await client.get(url, timeout=s.scrape_timeout)
    except BlockedHostError:
        raise
    except httpx.HTTPError as exc:
        raise DraftError("Could not fetch your draft URL. Check that it is public.") from exc
    finally:
        if rt.http is None:
            await client.aclose()
    if resp.status_code != 200:
        raise DraftError(f"Your draft URL returned HTTP {resp.status_code}.")
    if "html" not in resp.headers.get("content-type", "html").lower():
        raise DraftError("Your draft URL is not an HTML page.")
    page = await asyncio.to_thread(extract_page, resp.text, url, 0)
    if page is None or page.word_count < MIN_WORDS:
        n = page.word_count if page else 0
        raise DraftError(
            f"Your draft URL has too little readable text ({n} words; need {MIN_WORDS})."
        )
    meta = trafilatura.extract_metadata(resp.text)
    return draft_from_page(page, getattr(meta, "description", None))


async def _scrape_competitors(
    serp: SerpData, state: PipelineState, rt: Runtime
) -> list[ScrapedPage]:
    kw, country = state["keyword"], state["country"]
    with rt.session_factory() as db:
        cached = get_cached(db, "scrape", kw, country)
    if cached:
        pages = [ScrapedPage(**p) for p in cached["pages"]]
    else:
        pages = await scrape_pages(serp.results, settings=rt.settings, client=rt.http)
        with rt.session_factory() as db:
            set_cached(db, "scrape", kw, country, {"pages": [p.model_dump() for p in pages]})
    if state.get("draft_url"):  # do not compare the draft with itself
        pages = [p for p in pages if _norm_url(p.url) != _norm_url(state["draft_url"])]
    if len(pages) < rt.settings.min_pages:
        raise ScrapeError(
            f"Only {len(pages)} competitor pages were usable; need {rt.settings.min_pages}."
        )
    return pages


# ------------------------------------------------------------------ graph nodes
async def fetch_serp_node(state: PipelineState, config) -> dict[str, Any]:
    ctx: RunContext = config["configurable"]["ctx"]
    _emit(ctx, state, "searching", f"Searching the top results for “{state['keyword']}”")
    with ctx.rt.session_factory() as db:
        serp = await fetch_serp(
            state["keyword"], state["country"], settings=ctx.rt.settings, client=ctx.rt.http, db=db
        )
    return {"serp": serp}


async def scrape_pages_node(state: PipelineState, config) -> dict[str, Any]:
    ctx: RunContext = config["configurable"]["ctx"]
    _emit(ctx, state, "scraping", "Reading competitor pages and your draft")
    pages, draft = await asyncio.gather(
        _scrape_competitors(state["serp"], state, ctx.rt), load_draft(state, ctx.rt)
    )
    ctx.rt.broker.publish(
        state["analysis_id"], "scraping", f"Read {len(pages)} competitor pages", 45
    )
    return {"pages": pages, "draft": draft}


async def build_index_node(state: PipelineState, config) -> dict[str, Any]:
    ctx: RunContext = config["configurable"]["ctx"]
    _emit(ctx, state, "indexing", "Chunking and embedding competitor content")
    embedder = ctx.rt.embedder or await asyncio.to_thread(get_embedder)
    ctx.index = await asyncio.to_thread(build_index, state["pages"], embedder)
    return {}


async def analyze_draft_node(state: PipelineState, config) -> dict[str, Any]:
    ctx: RunContext = config["configurable"]["ctx"]
    _emit(ctx, state, "analyzing", "Finding content gaps and scoring your draft")
    result = await asyncio.to_thread(
        lambda: analyze_draft(
            keyword=state["keyword"], draft=state["draft"], pages=state["pages"],
            serp=state["serp"], index=ctx.index,
        )
    )  # fmt: skip
    return {"result": result}


async def generate_recommendations_node(state: PipelineState, config) -> dict[str, Any]:
    ctx: RunContext = config["configurable"]["ctx"]
    _emit(ctx, state, "generating", "Writing grounded recommendations")
    llm = ctx.rt.llm
    if llm is None:
        try:
            llm = get_llm(ctx.rt.settings)
        except LLMConfigError:
            llm = None
    result = await generate_recommendations(
        result=state["result"], draft=state["draft"], pages=state["pages"], index=ctx.index,
        llm=llm, settings=ctx.rt.settings,
    )  # fmt: skip
    return {"result": result}


async def finalize_node(state: PipelineState, config) -> dict[str, Any]:
    ctx: RunContext = config["configurable"]["ctx"]
    result = state["result"]
    with ctx.rt.session_factory() as db:
        row = db.get(Analysis, state["analysis_id"])
        if row is not None:
            row.status, row.stage, row.score = "done", "done", result.score
            row.result = result.model_dump(mode="json")
            row.error = None
            db.commit()
    ctx.rt.broker.publish(
        state["analysis_id"], "done", "Analysis complete", 100, status="done",
        data={"score": result.score, "llm_status": result.llm_status},
    )  # fmt: skip
    return {}


def build_graph():
    """linear graph: fetch_serp -> scrape_pages -> build_index -> analyze_draft ->
    generate_recommendations -> finalize (scoring happens inside analyze_draft)."""
    g = StateGraph(PipelineState)
    nodes = [
        ("fetch_serp", fetch_serp_node),
        ("scrape_pages", scrape_pages_node),
        ("build_index", build_index_node),
        ("analyze_draft", analyze_draft_node),
        ("generate_recommendations", generate_recommendations_node),
        ("finalize", finalize_node),
    ]
    for name, fn in nodes:
        g.add_node(name, fn)
    g.add_edge(START, nodes[0][0])
    for (a, _), (b, _) in zip(nodes, nodes[1:], strict=False):
        g.add_edge(a, b)
    g.add_edge(nodes[-1][0], END)
    return g.compile()


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


# ------------------------------------------------------------------ runner
def _fail(rt: Runtime, analysis_id: str, message: str) -> None:
    with rt.session_factory() as db:
        row = db.get(Analysis, analysis_id)
        if row is not None:
            row.status, row.error = "failed", message
            db.commit()
    rt.broker.publish(analysis_id, "error", message, 0, status="error")


async def run_analysis(analysis_id: str, rt: Runtime) -> None:
    """Execute the graph for one stored Analysis row; never raises."""
    with rt.session_factory() as db:
        row = db.get(Analysis, analysis_id)
        if row is None:
            return
        state: PipelineState = {
            "analysis_id": analysis_id, "keyword": row.keyword, "country": row.country,
            "draft_text": row.draft_text, "draft_url": row.draft_url,
            "draft_title": row.draft_title, "meta_description": row.meta_description,
        }  # fmt: skip
    ctx = RunContext(rt=rt)
    try:
        async with rt.semaphore:
            await get_graph().ainvoke(state, config={"configurable": {"ctx": ctx}})
    except USER_ERRORS + (DraftError,) as exc:
        _fail(rt, analysis_id, str(exc))
    except asyncio.CancelledError:
        _fail(rt, analysis_id, "The analysis was cancelled.")
        raise
    except Exception:
        log.exception("analysis failed", extra={"extra_fields": {"analysis_id": analysis_id}})
        _fail(rt, analysis_id, "Something went wrong while analysing. Please try again.")
    finally:
        if ctx.index is not None:
            ctx.index.close()


def start_analysis(analysis_id: str, rt: Runtime) -> asyncio.Task:
    """Schedule a run and keep a reference so the task is not garbage collected."""
    task = asyncio.create_task(run_analysis(analysis_id, rt))
    rt.tasks.add(task)
    task.add_done_callback(rt.tasks.discard)
    return task
