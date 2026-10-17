"""The user's draft in a normalised form (pasted text or scraped URL)."""

import re

from pydantic import BaseModel

from app.services.scraper import Heading, ScrapedPage, parse_markdown_sections

_HAS_HEADING = re.compile(r"^#{1,3}\s+\S", re.MULTILINE)


class Draft(BaseModel):
    """A draft with the on-page elements needed for scoring."""

    text: str  # full plain text incl. heading lines
    title: str | None = None
    meta_description: str | None = None
    h1: str | None = None
    headings: list[Heading] = []
    sections: list[tuple[str, str]] = []  # (heading, body) pairs used for chunking
    source: str = "text"  # text | url

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def has_title(self) -> bool:
        return bool(self.title)


def parse_draft_text(
    text: str, *, title: str | None = None, meta_description: str | None = None
) -> Draft:
    """Parse pasted text. Markdown-style '#', '##', '###' lines are read as headings."""
    text = text.strip()
    if _HAS_HEADING.search(text):
        headings, sections = parse_markdown_sections(text)
    else:
        headings, sections = [], []
    if sections or headings:
        pairs = [(s.heading, s.text) for s in sections]
        plain = "\n\n".join(f"{h}\n{b}" if h else b for h, b in pairs)
    else:
        pairs, plain = [("", text)], text
    h1 = next((h.text for h in headings if h.level == 1), None)
    return Draft(
        text=plain,
        title=(title or "").strip() or None,
        meta_description=(meta_description or "").strip() or None,
        h1=h1,
        headings=headings,
        sections=pairs,
        source="text",
    )


def draft_from_page(page: ScrapedPage, meta_description: str | None = None) -> Draft:
    """Build a Draft from a scraped URL."""
    return Draft(
        text=page.text,
        title=page.title or None,
        meta_description=meta_description,
        h1=next((h.text for h in page.headings if h.level == 1), None),
        headings=page.headings,
        sections=[(s.heading, s.text) for s in page.sections],
        source="url",
    )
