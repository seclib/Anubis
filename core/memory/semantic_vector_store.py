"""Explicit semantic vector-store layer for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.memory.retriever import RetrievalNamespace, RetrievalQuery, RetrievalResponse
from core.memory.vector_store import HashingEmbedder, InMemoryVectorStore
from core.memory.retriever import MemoryRetriever


@dataclass(slots=True)
class SemanticVectorStore:
    """Deterministic local vector index dedicated to semantic retrieval."""

    vector_store: InMemoryVectorStore = field(default_factory=InMemoryVectorStore)
    embedder: HashingEmbedder = field(default_factory=HashingEmbedder)
    retriever: MemoryRetriever = field(init=False)

    def __post_init__(self) -> None:
        self.retriever = MemoryRetriever(vector_store=self.vector_store, embedder=self.embedder)

    def index(
        self,
        *,
        document_id: str,
        text: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.vector_store.append(
            document_id=document_id,
            text=text,
            embedding=self.embedder.embed(text),
            metadata={
                "namespace": RetrievalNamespace.SEMANTIC,
                **dict(metadata or {}),
            },
        )

    def query(self, text: str, *, limit: int = 5) -> RetrievalResponse:
        return self.retriever.retrieve(
            RetrievalQuery(
                text=text,
                namespace=RetrievalNamespace.SEMANTIC,
                limit=limit,
            )
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": "semantic_vector_store",
            "vector_count": len(self.vector_store.all()),
            "local_only": True,
        }


__all__ = ["SemanticVectorStore"]
