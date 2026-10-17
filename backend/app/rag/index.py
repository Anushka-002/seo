"""Per-analysis in-memory Chroma index over competitor chunks."""

import uuid
from dataclasses import dataclass

import chromadb
import numpy as np
from chromadb.config import Settings as ChromaSettings

from app.rag.chunking import Chunk
from app.rag.embeddings import Embedder

_BATCH = 500


@dataclass(frozen=True)
class Hit:
    """A retrieved chunk with cosine similarity (1.0 = identical direction)."""

    chunk: Chunk
    score: float


class RagIndex:
    """Cosine-similarity vector index; also exposes raw vectors for clustering."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self._client = chromadb.EphemeralClient(ChromaSettings(anonymized_telemetry=False))
        self._name = f"analysis_{uuid.uuid4().hex}"
        self._col = self._client.create_collection(self._name, metadata={"hnsw:space": "cosine"})
        self._chunks: list[Chunk] = []
        self._matrix = np.zeros((0, embedder.dim), dtype=np.float32)

    @property
    def size(self) -> int:
        return len(self._chunks)

    @property
    def chunks(self) -> list[Chunk]:
        return list(self._chunks)

    @property
    def matrix(self) -> np.ndarray:
        """(n_chunks, dim) L2-normalised embeddings, aligned with `chunks`."""
        return self._matrix

    def add(self, chunks: list[Chunk]) -> None:
        """Embed and store chunks."""
        if not chunks:
            return
        vecs = self.embedder.embed([c.embed_text for c in chunks])
        for i in range(0, len(chunks), _BATCH):
            part = chunks[i : i + _BATCH]
            self._col.add(
                ids=[c.id for c in part],
                embeddings=vecs[i : i + _BATCH].tolist(),
                documents=[c.text for c in part],
                metadatas=[
                    {"source_url": c.source_url, "rank": c.rank, "heading": c.heading,
                     "chunk_index": c.chunk_index}
                    for c in part
                ],
            )  # fmt: skip
        self._chunks.extend(chunks)
        self._matrix = np.vstack([self._matrix, vecs])

    def query(self, text: str, k: int = 3) -> list[Hit]:
        """Top-k most similar chunks to `text`."""
        return self.query_vector(self.embedder.embed([text])[0], k)

    def query_vector(self, vector: np.ndarray, k: int = 3) -> list[Hit]:
        if not self._chunks:
            return []
        res = self._col.query(
            query_embeddings=[vector.tolist()], n_results=min(k, len(self._chunks))
        )
        by_id = {c.id: c for c in self._chunks}
        return [
            Hit(chunk=by_id[cid], score=float(1.0 - dist))
            for cid, dist in zip(res["ids"][0], res["distances"][0], strict=True)
        ]

    def close(self) -> None:
        """Free the collection."""
        try:
            self._client.delete_collection(self._name)
        except Exception:  # already gone
            pass
