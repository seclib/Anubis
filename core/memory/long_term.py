"""Long-term append-only memory for durable ANUBIS records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.memory.episodic import EpisodicMemory, EpisodicMemoryRecord
from core.memory.semantic import SemanticMemory, SemanticMemoryRecord


@dataclass(slots=True)
class LongTermMemory:
    """Durable split store for episodic execution and semantic knowledge."""

    episodic: EpisodicMemory = field(default_factory=EpisodicMemory)
    semantic: SemanticMemory = field(default_factory=SemanticMemory)

    def append_episode(
        self,
        *,
        event_type: str,
        actor: str,
        summary: str,
        payload: Mapping[str, Any] | None = None,
    ) -> EpisodicMemoryRecord:
        return self.episodic.append(
            event_type=event_type,
            actor=actor,
            summary=summary,
            payload=payload or {},
        )

    def append_fact(
        self,
        *,
        subject: str,
        predicate: str,
        value: str,
        confidence: float = 1.0,
        source: str = "system",
        metadata: Mapping[str, Any] | None = None,
    ) -> SemanticMemoryRecord:
        return self.semantic.append_fact(
            subject=subject,
            predicate=predicate,
            value=value,
            confidence=confidence,
            source=source,
            metadata=metadata or {},
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": "long_term",
            "episodic_count": len(self.episodic.all()),
            "semantic_count": len(self.semantic.all()),
            "append_only": True,
        }


__all__ = ["LongTermMemory"]
