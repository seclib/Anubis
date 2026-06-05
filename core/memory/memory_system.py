"""Memory-first ANUBIS memory system with strong layer separation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.memory.long_term import LongTermMemory
from core.memory.semantic_vector_store import SemanticVectorStore
from core.memory.short_term import ShortTermMemory


@dataclass(slots=True)
class MemorySystem:
    """Explicitly separated short-term, long-term, and semantic-vector memory."""

    short_term: ShortTermMemory = field(default_factory=ShortTermMemory)
    long_term: LongTermMemory = field(default_factory=LongTermMemory)
    semantic_vectors: SemanticVectorStore = field(default_factory=SemanticVectorStore)

    def remember_short_term(
        self,
        *,
        key: str,
        value: Mapping[str, Any],
        actor: str = "system",
    ) -> dict[str, Any]:
        return self.short_term.remember(key=key, value=value, actor=actor).to_dict()

    def remember_fact(
        self,
        *,
        subject: str,
        predicate: str,
        value: str,
        confidence: float = 1.0,
        source: str = "system",
        metadata: Mapping[str, Any] | None = None,
        index: bool = True,
    ) -> dict[str, Any]:
        record = self.long_term.append_fact(
            subject=subject,
            predicate=predicate,
            value=value,
            confidence=confidence,
            source=source,
            metadata=metadata or {},
        )
        if index:
            self.semantic_vectors.index(
                document_id=record.record_id,
                text=record.text,
                metadata={"record_id": record.record_id, "subject": subject, "predicate": predicate},
            )
        return record.to_dict()

    def snapshot(self) -> dict[str, Any]:
        return {
            "short_term": self.short_term.snapshot(),
            "long_term": self.long_term.snapshot(),
            "semantic_vectors": self.semantic_vectors.snapshot(),
            "separation": "strong",
        }


__all__ = ["MemorySystem"]
