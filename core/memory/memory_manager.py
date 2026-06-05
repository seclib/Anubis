"""Integrated append-only memory manager for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.memory.episodic import EpisodicMemory, EpisodicMemoryRecord
from core.memory.retriever import MemoryRetriever, RetrievalNamespace, RetrievalQuery, RetrievalResponse
from core.memory.semantic import SemanticMemory, SemanticMemoryRecord
from core.memory.vector_store import HashingEmbedder, InMemoryVectorStore


@dataclass(slots=True)
class MemoryManager:
    """Coordinates append-only memories and deterministic retrieval."""

    episodic: EpisodicMemory = field(default_factory=EpisodicMemory)
    semantic: SemanticMemory = field(default_factory=SemanticMemory)
    vector_store: InMemoryVectorStore = field(default_factory=InMemoryVectorStore)
    embedder: HashingEmbedder = field(default_factory=HashingEmbedder)
    retriever: MemoryRetriever = field(init=False)

    def __post_init__(self) -> None:
        self.retriever = MemoryRetriever(
            vector_store=self.vector_store,
            embedder=self.embedder,
        )

    def append_episode(
        self,
        *,
        event_type: str,
        actor: str,
        summary: str,
        payload: Mapping[str, Any] | None = None,
        index: bool = False,
    ) -> EpisodicMemoryRecord:
        record = self.episodic.append(
            event_type=event_type,
            actor=actor,
            summary=summary,
            payload=payload or {},
        )
        if index:
            text = f"{record.event_type} {record.actor} {record.summary}"
            embedding = self.embedder.embed(text)
            self.vector_store.append(
                document_id=record.record_id,
                text=text,
                embedding=embedding,
                metadata={
                    "namespace": RetrievalNamespace.EPISODIC,
                    "record_id": record.record_id,
                    "event_type": record.event_type,
                    "actor": record.actor,
                },
            )
        return record

    def append_fact(
        self,
        *,
        subject: str,
        predicate: str,
        value: str,
        confidence: float = 1.0,
        source: str = "system",
        metadata: Mapping[str, Any] | None = None,
        supersedes: str | None = None,
        index: bool = True,
    ) -> SemanticMemoryRecord:
        record = self.semantic.append_fact(
            subject=subject,
            predicate=predicate,
            value=value,
            confidence=confidence,
            source=source,
            metadata=metadata or {},
            supersedes=supersedes,
        )
        if index:
            embedding = self.embedder.embed(record.text)
            self.vector_store.append(
                document_id=record.record_id,
                text=record.text,
                embedding=embedding,
                metadata={
                    "namespace": RetrievalNamespace.SEMANTIC,
                    "record_id": record.record_id,
                    "subject": record.subject,
                    "predicate": record.predicate,
                    "source": record.source,
                },
            )
        return record

    def retrieve(
        self,
        text: str,
        *,
        namespace: RetrievalNamespace = RetrievalNamespace.ALL,
        limit: int = 5,
        metadata_filter: Mapping[str, Any] | None = None,
    ) -> RetrievalResponse:
        return self.retriever.retrieve(
            RetrievalQuery(
                text=text,
                namespace=namespace,
                limit=limit,
                metadata_filter=metadata_filter or {},
            )
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "episodic_count": len(self.episodic.all()),
            "semantic_count": len(self.semantic.all()),
            "vector_count": len(self.vector_store.all()),
            "append_only": True,
        }


__all__ = ["MemoryManager"]
