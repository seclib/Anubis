from __future__ import annotations

import hashlib
import logging
import math
import os
from functools import lru_cache
from typing import Iterable

from rag.shared.config import config


logger = logging.getLogger("anubis.rag.shared.embedding")


class EmbeddingPipeline:
    def __init__(self, model_name: str | None = None, fallback_dimensions: int = 384) -> None:
        self.model_name = model_name or config.embedding_model
        self.dimensions = fallback_dimensions
        self._model = None
        self.provider = os.getenv("ANUBIS_RAG_EMBEDDING_PROVIDER", "hash").strip().lower()

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self.dimensions = int(self._model.get_sentence_embedding_dimension() or self.dimensions)
        return self._model

    @lru_cache(maxsize=50000)
    def embed(self, text: str) -> list[float]:
        clean = self._prepare(text)
        if self.provider in {"hash", "fallback", "deterministic"}:
            return self._fallback_embed(clean)
        try:
            vector = self.model.encode(clean, normalize_embeddings=True)
            return [float(value) for value in vector.tolist()]
        except Exception as exc:
            logger.warning("sentence-transformers embedding failed; using deterministic fallback: %s", exc)
            return self._fallback_embed(clean)

    def embed_batch(self, texts: Iterable[str], batch_size: int = 64) -> list[list[float]]:
        items = [self._prepare(text) for text in texts]
        if self.provider in {"hash", "fallback", "deterministic"}:
            return [self._fallback_embed(text) for text in items]
        vectors: list[list[float]] = []
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            try:
                encoded = self.model.encode(batch, normalize_embeddings=True, batch_size=batch_size)
                vectors.extend([[float(value) for value in row.tolist()] for row in encoded])
            except Exception as exc:
                logger.warning("batch embedding failed; using deterministic fallback: %s", exc)
                vectors.extend(self._fallback_embed(text) for text in batch)
        return vectors

    def cosine(self, left: list[float], right: list[float]) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    def _prepare(self, text: str) -> str:
        return " ".join(str(text or "").split())[:12000]

    def _fallback_embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


EmbeddingService = EmbeddingPipeline
