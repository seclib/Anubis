from __future__ import annotations

from anubis.core_life.swarm.agent_registry import AgentInsight
from anubis.memory import ConflictStrategy, MemoryAccess, MemoryKind, MemoryRecord, MemoryScope, SharedMemory


class SwarmMemory:
    """Shared research memory with deterministic conflict handling."""

    def __init__(self) -> None:
        self._memory = SharedMemory(conflict_strategy=ConflictStrategy.KEEP_BOTH)

    def write_insight(self, insight: AgentInsight, *, session_id: str) -> MemoryRecord:
        record = MemoryRecord(
            content=insight.summary,
            scope=MemoryScope.SWARM,
            scope_id=session_id,
            owner_id=insight.agent_name,
            kind=MemoryKind.SHORT_TERM,
            metadata={
                "role": insight.role.value,
                "recommendation": insight.recommendation,
                "confidence": insight.confidence,
                "evidence": insight.evidence,
            },
        )
        resolution = self._memory.put(record, actor_id=insight.agent_name)
        if resolution.record is None:
            raise ValueError(resolution.explanation)
        return resolution.record

    def recall(self, session_id: str, *, actor_id: str = "hive_mind") -> tuple[MemoryRecord, ...]:
        return self._memory.query_scope(
            MemoryAccess(
                actor_id=actor_id,
                scopes=frozenset({MemoryScope.SWARM}),
                scope_ids=frozenset({session_id}),
            )
        )
