"""Embedding pipeline for Qdrant-backed retrieval."""

from __future__ import annotations

from typing import Any

from config import EMBEDDING_MODEL
from memory import vector
from services.cache_manager import CacheManager, get_cache_manager


class EmbeddingPipeline:
    def __init__(self, cache: CacheManager | None = None, model: str = EMBEDDING_MODEL) -> None:
        self.cache = cache or get_cache_manager()
        self.model = model

    def embed_query(self, text: str) -> dict[str, Any]:
        return self.cache.get_embedding(
            text,
            model=self.model,
            embedder=vector._hash_embedding,
        )

    def embed_document(self, text: str) -> dict[str, Any]:
        return self.cache.get_embedding(
            text,
            model=self.model,
            embedder=vector._hash_embedding,
        )

    def embed_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        return [self.embed_document(text) for text in texts]


__all__ = ["EmbeddingPipeline"]

