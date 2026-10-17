"""Heading-aware chunking (~300 tokens, overlapping) with source metadata."""

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.scraper import ScrapedPage


@dataclass(frozen=True)
class Chunk:
    """A retrievable passage with provenance."""

    id: str
    text: str
    source_url: str
    rank: int
    heading: str
    chunk_index: int
    is_intro: bool = False  # text under the H1 / before the first heading

    @property
    def embed_text(self) -> str:
        """Text used for embedding: the section heading gives each passage its topic."""
        return f"{self.heading}. {self.text}" if self.heading else self.text


def estimate_tokens(text: str) -> int:
    """Cheap offline token estimate (~1.33 tokens per word)."""
    return int(len(text.split()) * 1.33) + 1


def _splitter(chunk_tokens: int, overlap_tokens: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_tokens,
        chunk_overlap=overlap_tokens,
        length_function=estimate_tokens,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def chunk_text(
    text: str,
    *,
    source_url: str,
    rank: int = 0,
    heading: str = "",
    is_intro: bool = False,
    start_index: int = 0,
    chunk_tokens: int = 300,
    overlap_tokens: int = 50,
    min_tokens: int = 40,
) -> list[Chunk]:
    """Split one block of text; tiny fragments are dropped unless they are all there is."""
    pieces = [p.strip() for p in _splitter(chunk_tokens, overlap_tokens).split_text(text)]
    pieces = [p for p in pieces if p]
    kept = [p for p in pieces if estimate_tokens(p) >= min_tokens] or pieces
    return [
        Chunk(
            id=f"{source_url}#{rank}-{start_index + i}",
            text=p, source_url=source_url, rank=rank, heading=heading,
            chunk_index=start_index + i, is_intro=is_intro,
        )
        for i, p in enumerate(kept)
    ]  # fmt: skip


def chunk_page(page: ScrapedPage, **kwargs) -> list[Chunk]:
    """Chunk every section of a page, carrying the section heading as metadata."""
    chunks: list[Chunk] = []
    for section in page.sections:
        chunks.extend(
            chunk_text(
                section.text,
                source_url=page.url,
                rank=page.rank,
                heading=section.heading,
                is_intro=section.level <= 1,
                start_index=len(chunks),
                **kwargs,
            )
        )
    return chunks
