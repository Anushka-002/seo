"""Export real backend results as frontend test fixtures (keeps TS types honest).

Run from backend/:  PYTHONPATH=. python scripts/export_fixtures.py
"""

import asyncio
import json
from pathlib import Path

from app.core.config import Settings
from app.rag.analyzer import analyze_draft
from app.rag.draft import parse_draft_text
from app.services.recommend import generate_recommendations
from tests.helpers import KW, SAMPLE, FakeLLM, load_corpus

OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "test" / "fixtures"


async def build(text: str, llm, **kw) -> dict:
    pages, serp, index = load_corpus()
    draft = parse_draft_text(text, **kw)
    result = analyze_draft(keyword=KW, draft=draft, pages=pages, serp=serp, index=index)
    result = await generate_recommendations(
        result=result, draft=draft, pages=pages, index=index, llm=llm,
        settings=Settings(database_url="sqlite://"),
    )  # fmt: skip
    index.close()
    return result.model_dump(mode="json")


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    weak = (SAMPLE / "drafts" / "weak.txt").read_text()
    strong = (SAMPLE / "drafts" / "strong.md").read_text()
    meta = {"title": "Best Running Shoes: Buyer's Guide", "meta_description": "Pick running shoes."}
    fixtures = {
        "weak": await build(weak, FakeLLM(), title="Shoes", meta_description="All about shoes"),
        "strong": await build(strong, FakeLLM(), **meta),
        "no_llm": await build(weak, None),
    }
    for name, data in fixtures.items():
        (OUT / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"wrote {name}.json  score={data['score']} recs={len(data['recommendations'])}")


if __name__ == "__main__":
    asyncio.run(main())
