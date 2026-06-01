"""RAG service facade backed by the hybrid retrieval engine."""

from __future__ import annotations

from typing import Any

from retrieval.service import RetrievalService, get_retrieval_service


class RAGService:
    def __init__(self, retrieval: RetrievalService | None = None) -> None:
        self.retrieval = retrieval or get_retrieval_service()

    def health(self) -> dict[str, Any]:
        return self.retrieval.health()

    def query(
        self,
        query: str,
        *,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
        generate_answer: bool = False,
    ) -> dict[str, Any]:
        return self.retrieval.retrieve(
            query,
            top_k=top_k,
            filters=filters or {},
            generate_answer=generate_answer,
        )

    def ingest(
        self,
        *,
        title: str,
        content: str,
        source_url: str | None = None,
        folder: str = "Ingested",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.retrieval.ingest(
            title=title,
            content=content,
            source_url=source_url,
            folder=folder,
            metadata=metadata or {},
        )

    def ensure_qdrant(self, *, recreate: bool = False) -> dict[str, Any]:
        return self.retrieval.ensure_qdrant(recreate=recreate)

    def index_qdrant(self, *, limit: int | None = None) -> dict[str, Any]:
        return self.retrieval.index_qdrant(limit=limit)

    def ingest_obsidian(
        self,
        *,
        limit: int | None = None,
        force: bool = False,
        index_qdrant: bool = True,
    ) -> dict[str, Any]:
        return self.retrieval.obsidian.ingest(
            limit=limit,
            force=force,
            index_qdrant=index_qdrant,
        )


_SERVICE: RAGService | None = None


def get_rag_service() -> RAGService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = RAGService()
    return _SERVICE


__all__ = ["RAGService", "get_rag_service"]
