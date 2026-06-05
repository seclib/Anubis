"""Semantic knowledge memory."""

from anubis.memory import MemoryAccess, MemoryKind, MemoryRecord, MemoryScope, SharedMemory


def semantic_record(content: str, *, owner_id: str = "system") -> MemoryRecord:
    return MemoryRecord(
        content=content,
        scope=MemoryScope.GLOBAL,
        scope_id="global",
        owner_id=owner_id,
        kind=MemoryKind.SEMANTIC,
    )


class SemanticMemory(SharedMemory):
    def remember(self, content: str, *, owner_id: str = "system") -> MemoryRecord:
        resolution = self.put(semantic_record(content, owner_id=owner_id), actor_id=owner_id)
        if resolution.record is None:
            raise ValueError(resolution.explanation)
        return resolution.record

    def recall(self, query: str = "", *, actor_id: str = "system", limit: int = 10) -> tuple[MemoryRecord, ...]:
        access = MemoryAccess(actor_id=actor_id, scopes=frozenset({MemoryScope.GLOBAL}))
        records = self.query_scope(access)
        if query:
            lowered = query.lower()
            records = tuple(record for record in records if lowered in record.content.lower())
        return tuple(sorted(records, key=lambda record: record.created_at, reverse=True)[:limit])
