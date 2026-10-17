"""Command-line tools to exercise the Phase 2 pipeline.

Examples:
  python -m app.cli serp "best running shoes"
  python -m app.cli index "best running shoes" --query "how long do shoes last"
  python -m app.cli index "best running shoes" --fixtures sample_data/pages --embedder hashing
"""

import argparse
import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.core.db import SessionLocal, init_db
from app.rag.analyzer import analyze_draft
from app.rag.draft import parse_draft_text
from app.rag.embeddings import get_embedder
from app.services.ingest import build_competitor_index, build_index
from app.services.scraper import extract_page
from app.services.serp import SerpData, SerpResult, fetch_serp


def _print_hits(index, query: str, k: int) -> None:
    print(f"\nTop {k} passages for: {query!r}")
    for hit in index.query(query, k):
        c = hit.chunk
        snippet = " ".join(c.text.split())[:140]
        where = f"#{c.rank} {c.source_url} :: {c.heading or '(intro)'}"
        print(f"  [{hit.score:.2f}] {where}")
        print(f"        {snippet}...")


def _print_analysis(r) -> None:
    print(f"\nSEO SCORE: {r.score}/100   (embedder: {r.embedder}, {r.n_clusters} subtopics)")
    for c in r.components:
        print(f"  {c.name:<27}{c.score:>5.1f}/{c.max_score:<4.0f}{c.reason}")
    gaps = [t for t in r.topics if t.is_gap]
    print(f"\nContent gaps ({len(gaps)}):")
    for t in gaps:
        print(f"  [{t.severity}] {t.label}  (on {t.page_count} pages, coverage {t.coverage:.0%})")
    missing = [k.phrase for k in r.keyphrases if not k.in_draft]
    print(f"\nMissing phrases: {', '.join(missing[:12]) or 'none'}")
    print(f"Intent: SERP={r.serp_intent.primary} draft={r.draft_intent.primary}")


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    if args.cmd == "serp":
        init_db()
        with SessionLocal() as db:
            data = await fetch_serp(args.keyword, args.country, settings=settings, db=db)
        print(
            f"{len(data.results)} results via {'serper' if settings.use_serper else 'duckduckgo'}"
        )
        for r in data.results:
            print(f"  {r.rank:>2}. {r.title[:70]}\n      {r.url}")
        if data.related_searches:
            print("related:", "; ".join(data.related_searches[:6]))
        return

    embedder = get_embedder(args.embedder)
    draft_text = Path(args.draft).read_text(encoding="utf-8") if args.cmd == "analyze" else None
    if args.fixtures:
        files = sorted(Path(args.fixtures).glob("*.html"))
        pages = []
        for i, f in enumerate(files, 1):
            page = extract_page(f.read_text(encoding="utf-8"), f"https://{f.stem}/", i)
            if page and page.word_count >= settings.min_page_words:
                pages.append(page)
        serp = SerpData(
            keyword=args.keyword, country=args.country,
            results=[SerpResult(rank=p.rank, title=p.title, url=p.url) for p in pages],
        )  # fmt: skip
        index = build_index(pages, embedder)
        print(f"[offline fixtures] {len(files)} files, {len(files) - len(pages)} dropped as thin")
    else:
        init_db()
        with SessionLocal() as db:
            res = await build_competitor_index(
                args.keyword, args.country, settings=settings, db=db, embedder=embedder
            )
        pages, serp, index = res.pages, res.serp, res.index

    print(f"keyword={args.keyword!r} pages={len(pages)}/{len(serp.results)} "
          f"chunks={index.size} embedder={embedder.name} dim={embedder.dim}")  # fmt: skip
    for p in pages:
        print(f"  #{p.rank} {p.word_count:>5} words  {len(p.headings):>2} headings  {p.url}")
    if args.cmd == "analyze":
        draft = parse_draft_text(draft_text, title=args.title, meta_description=args.meta)
        result = analyze_draft(
            keyword=args.keyword, draft=draft, pages=pages, serp=serp, index=index
        )
        if args.json:
            print(result.model_dump_json(indent=2))
        else:
            _print_analysis(result)
    elif args.query:
        _print_hits(index, args.query, args.k)
    index.close()


def main() -> None:
    ap = argparse.ArgumentParser(prog="ranklens")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("serp", "index", "analyze"):
        p = sub.add_parser(name)
        p.add_argument("keyword")
        p.add_argument("--country", default="us")
        if name == "analyze":
            p.add_argument("--draft", required=True, help="path to a .txt/.md draft")
            p.add_argument("--title")
            p.add_argument("--meta", help="meta description")
            p.add_argument("--json", action="store_true", help="print the full JSON result")
        if name == "index":
            p.add_argument("--query", help="run a retrieval query against the built index")
            p.add_argument("-k", type=int, default=3)
        if name in ("index", "analyze"):
            p.add_argument("--fixtures", help="read *.html from a folder instead of the network")
            p.add_argument("--embedder", choices=["sbert", "hashing"], default=None)
    asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    main()
