"""Regenerate the bundled demo with a REAL run (live SERP + scraping + LLM).

Run from backend/ with keys in .env (SERPER_API_KEY and GROQ_API_KEY or GEMINI_API_KEY):

    PYTHONPATH=. python scripts/build_demo.py
    PYTHONPATH=. python scripts/build_demo.py --keyword "best running shoes" --draft my.md

Writes app/data/demo_analysis.json, which POST /api/demo serves. Refuses to overwrite the
bundled file if the run did not use the LLM, so the live demo never regresses to templates.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.db import SessionLocal, init_db
from app.models import Analysis
from app.services.demo import DEMO_FILE
from app.services.pipeline import Runtime, run_analysis

DEFAULT_DRAFT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "example.ts"


def default_draft() -> str:
    """The same deliberately average draft as the 'Try an example draft' button."""
    src = DEFAULT_DRAFT.read_text(encoding="utf-8")
    start = src.index("`") + 1
    return src[start : src.index("`", start)]


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keyword", default="best running shoes")
    ap.add_argument("--draft", type=Path, help="markdown/text file; default = example draft")
    ap.add_argument("--allow-no-llm", action="store_true", help="write even if the LLM was off")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.use_serper:
        print("note: SERPER_API_KEY is empty, using the DuckDuckGo fallback")
    init_db()
    draft = args.draft.read_text(encoding="utf-8") if args.draft else default_draft()
    row_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(Analysis(id=row_id, keyword=args.keyword, draft_text=draft, status="pending"))
        db.commit()
    await run_analysis(row_id, Runtime(settings=settings))
    with SessionLocal() as db:
        row = db.get(Analysis, row_id)
        if row is None or row.status != "done" or not row.result:
            print(f"analysis failed: {row.error if row else 'row missing'}")
            return 1
        result = dict(row.result)
        db.delete(row)
        db.commit()
    if result.get("llm_status") != "ok" and not args.allow_no_llm:
        print(f"LLM status was {result.get('llm_status')!r}: {result.get('llm_message')}")
        print("Not writing the demo. Fix the key/quota or pass --allow-no-llm.")
        return 1
    DEMO_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEMO_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {DEMO_FILE}  score={result['score']}  recs={len(result['recommendations'])}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
