"""Shared test doubles: a prompt-aware fake LLM, a mock website, and the sample corpus."""

import json
import re
from collections.abc import Callable
from pathlib import Path

import httpx

from app.rag.embeddings import HashingEmbedder
from app.services.ingest import build_index
from app.services.scraper import extract_page
from app.services.serp import SerpData, SerpResult

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data"
KW = "best running shoes"
TOPIC_RE = re.compile(r'<topic id="(\d+)"[^>]*>(.*?)</topic>', re.DOTALL)
SOURCE_RE = re.compile(r'<source n="(\d+)"')


def load_corpus():
    """(pages, serp, index) built from the sample competitor pages with the offline embedder."""
    pages = []
    for i, f in enumerate(sorted((SAMPLE / "pages").glob("*.html")), 1):
        p = extract_page(f.read_text(encoding="utf-8"), f"https://{f.stem}/", i)
        if p and p.word_count >= 150:
            pages.append(p)
    serp = SerpData(
        keyword=KW, country="us",
        results=[SerpResult(rank=p.rank, title=p.title, url=p.url) for p in pages],
    )  # fmt: skip
    return pages, serp, build_index(pages, HashingEmbedder())


# ---------------------------------------------------------------- fake LLM
def good_gaps(user: str) -> str:
    items = []
    for cid, body in TOPIC_RE.findall(user):
        n = SOURCE_RE.findall(body)[0]
        items.append(
            {
                "cluster_id": int(cid),
                "heading_suggestion": f"Section for topic {cid}",
                "recommendation": f"Add a section covering this topic as competitors do [{n}]. "
                "Explain the key points clearly and give practical examples.",
            }
        )
    return json.dumps({"items": items})


def good_seo(user: str) -> str:
    kw = re.search(r"Target keyword: (.+)", user).group(1).strip()
    return json.dumps(
        {
            "title": f"{kw.title()}: A Practical Guide"[:60],
            "meta_description": f"Learn how to choose the {kw}: cushioning, fit, price and "
            "lifespan explained simply.",
            "outline": [
                {"level": 2, "heading": f"How to choose {kw}", "notes": "intro"},
                {"level": 2, "heading": "Cushioning", "notes": ""},
                {"level": 2, "heading": "Fit", "notes": ""},
                {"level": 3, "heading": "Road vs trail", "notes": ""},
                {"level": 2, "heading": "Price and value", "notes": ""},
                {"level": 2, "heading": "How long they last", "notes": ""},
            ],
        }
    )


def good_labels(user: str) -> str:
    ids = re.findall(r'<topic id="(\d+)"', user)
    return json.dumps({"labels": [{"cluster_id": int(i), "label": f"Topic {i}"} for i in ids]})


class FakeLLM:
    """Routes by system prompt; each handler is a str, callable(user)->str, Exception or list."""

    name = "fake"

    def __init__(self, gaps=good_gaps, seo=good_seo, labels=good_labels) -> None:
        self.handlers: dict[str, object] = {"gaps": gaps, "seo": seo, "labels": labels}
        self.calls: list[tuple[str, str, str]] = []  # (kind, system, user)

    async def complete(self, system: str, user: str, **kwargs) -> str:
        kind = (
            "labels" if "You name topics" in system
            else "gaps" if "content strategist" in system else "seo"
        )  # fmt: skip
        self.calls.append((kind, system, user))
        h = self.handlers[kind]
        if isinstance(h, list):
            h = h.pop(0)
        out = h(user) if callable(h) else h
        if isinstance(out, Exception):
            raise out
        return out

    def kinds(self) -> list[str]:
        return [c[0] for c in self.calls]


# ---------------------------------------------------------------- mock website
def md_to_html(md: str, title: str = "My Draft") -> str:
    out = []
    for block in md.strip().split("\n\n"):
        if block.startswith("### "):
            out.append(f"<h3>{block[4:]}</h3>")
        elif block.startswith("## "):
            out.append(f"<h2>{block[3:]}</h2>")
        elif block.startswith("# "):
            out.append(f"<h1>{block[2:]}</h1>")
        else:
            out.append(f"<p>{block}</p>")
    body = "".join(out)
    return f"<html><head><title>{title}</title></head><body><article>{body}</article></body></html>"


def make_site(
    pages_html: dict[str, str],
    *,
    serper_status: int = 200,
    extra_pages: dict[str, tuple[int, str]] | None = None,
    counters: dict | None = None,
    organic_hosts: list[str] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Serper + competitor pages (+ extra hosts as {host: (status, html)})."""
    counters = counters if counters is not None else {}
    hosts = organic_hosts if organic_hosts is not None else list(pages_html)

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "google.serper.dev":
            counters["serper"] = counters.get("serper", 0) + 1
            if serper_status != 200:
                return httpx.Response(serper_status)
            organic = [{"title": h, "link": f"https://{h}/post", "snippet": ""} for h in hosts]
            return httpx.Response(200, json={"organic": organic})
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        counters["pages"] = counters.get("pages", 0) + 1
        if extra_pages and host in extra_pages:
            status, html = extra_pages[host]
            return httpx.Response(status, text=html, headers={"content-type": "text/html"})
        if host in pages_html:
            return httpx.Response(200, text=pages_html[host], headers={"content-type": "text/html"})
        return httpx.Response(404)

    return handler
