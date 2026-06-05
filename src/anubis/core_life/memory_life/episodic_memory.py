"""Execution episode memory."""

from anubis.memory import MemoryAccess, MemoryKind, MemoryRecord, MemoryScope, SharedMemory


class EpisodicMemory(SharedMemory):
    def episode(self, content: str, *, scope_id: str, owner_id: str) -> MemoryRecord:
        return MemoryRecord(
            content=content,
            scope=MemoryScope.TASK,
            scope_id=scope_id,
            owner_id=owner_id,
            kind=MemoryKind.SHORT_TERM,
        )

    def recent(self, *, actor_id: str = "principal_loop", limit: int = 5) -> tuple[MemoryRecord, ...]:
        records = self.query_scope(
            MemoryAccess(
                actor_id=actor_id,
                scopes=frozenset({MemoryScope.TASK}),
                scope_ids=frozenset(record.scope_id for record in self._records.values()),
            )
        )
        return tuple(sorted(records, key=lambda record: record.created_at, reverse=True)[:limit])
