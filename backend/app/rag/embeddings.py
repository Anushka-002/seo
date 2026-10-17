"""Embedding backends: sentence-transformers (default) and an offline hashing fallback."""

import re
import zlib
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.core.config import get_settings

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an the and or but of to in on for with at by from is are was were be been it this that "
    "as you your we our i they their he she his her its not no so if then than too very can "
    "will just do does did have has had".split()
)


class Embedder(Protocol):
    """Anything that turns texts into L2-normalised vectors."""

    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    """Deterministic bag-of-words hashing embedder (no downloads). For tests/offline use only."""

    name = "hashing"

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for tok in _TOKEN.findall(text.lower()):
                if tok in _STOP or len(tok) < 2:
                    continue
                h = zlib.crc32(tok.encode())
                out[row, h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1.0, norms)


class SentenceTransformerEmbedder:
    """all-MiniLM-L6-v2 via sentence-transformers (runs locally, no API key)."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # lazy: heavy import

        self._model = SentenceTransformer(model_name)
        self.name = model_name
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        self.dim = int(get_dim())

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(
            texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vecs, dtype=np.float32)


@lru_cache
def get_embedder(kind: str | None = None) -> Embedder:
    """Return the configured embedder (cached so the model loads once per process)."""
    s = get_settings()
    kind = (kind or s.embedder).lower()
    if kind == "hashing":
        return HashingEmbedder()
    if kind == "sbert":
        return SentenceTransformerEmbedder(s.embedding_model)
    raise ValueError(f"Unknown embedder '{kind}' (use 'sbert' or 'hashing')")
