"""Deterministic retrieval facade for ANUBIS memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from core.memory.vector_store import Embedder, HashingEmbedder, VectorSearchResult, VectorStore


class RetrievalNamespace(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    ALL = "all"


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    text: str
    namespace: RetrievalNamespace = RetrievalNamespace.ALL
    limit: int = 5
    metadata_filter: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        text = self.text.strip()
        if not text:
            raise ValueError("query text cannot be empty")
        if self.limit < 1:
            raise ValueError("limit must be at least 1")
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "metadata_filter", MappingProxyType(dict(self.metadata_filter)))


@dataclass(frozen=True, slots=True)
class RetrievalResponse:
    query: RetrievalQuery
    embedding_model: str
    results: tuple[VectorSearchResult, ...]
    explanation: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": {
                "text": self.query.text,
                "namespace": self.query.namespace,
                "limit": self.query.limit,
                "metadata_filter": dict(self.query.metadata_filter),
            },
            "embedding_model": self.embedding_model,
            "results": [result.to_dict() for result in self.results],
            "explanation": list(self.explanation),
        }


class MemoryRetriever:
    """Routes vector retrieval requests over an abstract vector store."""

    def __init__(
        self,
        *,
        vector_store: VectorStore,
        embedder: Embedder | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedder = embedder or HashingEmbedder()

    def retrieve(self, query: RetrievalQuery) -> RetrievalResponse:
        embedding = self.embedder.embed(query.text)
        raw_results = self.vector_store.search(embedding, limit=max(query.limit * 3, query.limit))
        filtered = [
            result
            for result in raw_results
            if self._matches_namespace(result, query.namespace)
            and self._matches_metadata(result, query.metadata_filter)
        ]
        ranked = tuple(
            sorted(
                filtered,
                key=lambda result: (
                    -result.score,
                    result.document.sequence,
                    result.document.document_id,
                ),
            )[: query.limit]
        )
        return RetrievalResponse(
            query=query,
            embedding_model=embedding.model,
            results=ranked,
            explanation=(
                f"Embedded query with {embedding.model}.",
                f"Filtered namespace={query.namespace}.",
                "Ranked by score descending, then append sequence, then document id.",
            ),
        )

    @staticmethod
    def _matches_namespace(result: VectorSearchResult, namespace: RetrievalNamespace) -> bool:
        if namespace == RetrievalNamespace.ALL:
            return True
        return result.document.metadata.get("namespace") == namespace

    @staticmethod
    def _matches_metadata(
        result: VectorSearchResult,
        metadata_filter: Mapping[str, Any],
    ) -> bool:
        return all(result.document.metadata.get(key) == value for key, value in metadata_filter.items())


__all__ = [
    "MemoryRetriever",
    "RetrievalNamespace",
    "RetrievalQuery",
    "RetrievalResponse",
]
