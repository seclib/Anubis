from __future__ import annotations

from anubis import (
    ConflictStatus,
    ConflictStrategy,
    MemoryAccess,
    MemoryKind,
    MemoryKindPolicy,
    MemoryRecord,
    MemoryScope,
    Sensitivity,
    SharedMemory,
)


def test_memory_isolation_filters_scope_and_sensitivity() -> None:
    memory = SharedMemory()
    visible = MemoryRecord(
        id="mem_visible",
        content="visible",
        scope=MemoryScope.SWARM,
        scope_id="swarm-1",
        owner_id="agent-a",
        sensitivity=Sensitivity.INTERNAL,
    )
    secret = MemoryRecord(
        id="mem_secret",
        content="secret",
        scope=MemoryScope.SWARM,
        scope_id="swarm-1",
        owner_id="agent-b",
        sensitivity=Sensitivity.SECRET,
    )
    memory.put(visible)
    memory.put(secret)

    access = MemoryAccess(
        actor_id="agent-a",
        scopes=frozenset({MemoryScope.SWARM}),
        scope_ids=frozenset({"swarm-1"}),
        max_sensitivity=Sensitivity.INTERNAL,
    )

    assert memory.get("mem_visible", access) == visible
    assert memory.get("mem_secret", access) is None
    assert memory.query_scope(access) == (visible,)


def test_rejects_stale_write_by_default() -> None:
    memory = SharedMemory()
    original = MemoryRecord(
        id="mem_1",
        content="original",
        scope=MemoryScope.GLOBAL,
        scope_id="global",
        owner_id="agent",
    )
    memory.put(original)
    current = memory.put(
        MemoryRecord(
            id="mem_1",
            content="current",
            scope=MemoryScope.GLOBAL,
            scope_id="global",
            owner_id="agent",
        ),
        expected_version=1,
    ).record

    rejected = memory.put(
        MemoryRecord(
            id="mem_1",
            content="stale",
            scope=MemoryScope.GLOBAL,
            scope_id="global",
            owner_id="agent",
        ),
        expected_version=1,
    )

    assert current is not None
    assert rejected.status == ConflictStatus.REJECTED
    assert rejected.record == current
    assert rejected.conflict_record is not None
    assert rejected.conflict_record.content == "stale"


def test_merge_metadata_conflict_resolution() -> None:
    memory = SharedMemory()
    memory.put(
        MemoryRecord(
            id="mem_1",
            content="original",
            scope=MemoryScope.GLOBAL,
            scope_id="global",
            owner_id="agent",
            metadata={"a": 1},
        )
    )
    memory.put(
        MemoryRecord(
            id="mem_1",
            content="current",
            scope=MemoryScope.GLOBAL,
            scope_id="global",
            owner_id="agent",
            metadata={"b": 2},
        ),
        expected_version=1,
    )

    resolved = memory.put(
        MemoryRecord(
            id="mem_1",
            content="incoming",
            scope=MemoryScope.GLOBAL,
            scope_id="global",
            owner_id="agent",
            metadata={"c": 3},
        ),
        expected_version=1,
        strategy=ConflictStrategy.MERGE_METADATA,
    )

    assert resolved.status == ConflictStatus.RESOLVED
    assert resolved.record is not None
    assert resolved.record.content == "incoming"
    assert dict(resolved.record.metadata) == {"b": 2, "c": 3}


def test_keep_both_conflict_resolution_forks_record() -> None:
    memory = SharedMemory()
    memory.put(
        MemoryRecord(
            id="mem_1",
            content="original",
            scope=MemoryScope.GLOBAL,
            scope_id="global",
            owner_id="agent",
        )
    )
    memory.put(
        MemoryRecord(
            id="mem_1",
            content="current",
            scope=MemoryScope.GLOBAL,
            scope_id="global",
            owner_id="agent",
        ),
        expected_version=1,
    )

    forked = memory.put(
        MemoryRecord(
            id="mem_1",
            content="incoming",
            scope=MemoryScope.GLOBAL,
            scope_id="global",
            owner_id="agent",
        ),
        expected_version=1,
        strategy=ConflictStrategy.KEEP_BOTH,
    )

    assert forked.status == ConflictStatus.FORKED
    assert forked.conflict_record is not None
    assert forked.conflict_record.parent_id == "mem_1"
    assert forked.conflict_record.content == "incoming"


def test_vector_search_and_sync_cursor() -> None:
    source = SharedMemory()
    target = SharedMemory()
    record_a = MemoryRecord(
        id="mem_a",
        content="alpha",
        scope=MemoryScope.GLOBAL,
        scope_id="global",
        owner_id="agent",
        sensitivity=Sensitivity.PUBLIC,
    )
    record_b = MemoryRecord(
        id="mem_b",
        content="beta",
        scope=MemoryScope.GLOBAL,
        scope_id="global",
        owner_id="agent",
        sensitivity=Sensitivity.PUBLIC,
    )
    source.put(record_a, vector=(1, 0))
    source.put(record_b, vector=(0, 1))
    target.put(record_a)
    target.put(record_b)

    batch = source.vector_sync(after_cursor=0)
    applied = target.apply_vector_sync(batch)
    access = MemoryAccess(
        actor_id="agent",
        scopes=frozenset({MemoryScope.GLOBAL}),
        max_sensitivity=Sensitivity.PUBLIC,
    )
    results = target.search((1, 0), access)

    assert applied == 2
    assert batch.cursor == 2
    assert results[0].record.id == "mem_a"
    assert results[0].score == 1.0


def test_memory_kind_definitions_are_explicit() -> None:
    policy = MemoryKindPolicy()

    short_term = policy.definition(MemoryKind.SHORT_TERM)
    long_term = policy.definition(MemoryKind.LONG_TERM)
    semantic = policy.definition(MemoryKind.SEMANTIC)
    procedural = policy.definition(MemoryKind.PROCEDURAL)

    assert short_term.durable is False
    assert long_term.durable is True
    assert semantic.vector_indexed is True
    assert procedural.vector_indexed is False
    assert "playbooks" in procedural.description


def test_procedural_memory_does_not_vector_index_by_default() -> None:
    memory = SharedMemory()
    record = MemoryRecord(
        id="mem_proc",
        content="rollback checklist",
        scope=MemoryScope.GLOBAL,
        scope_id="global",
        owner_id="agent",
        kind=MemoryKind.PROCEDURAL,
        sensitivity=Sensitivity.PUBLIC,
    )

    memory.put(record, vector=(1, 0))
    access = MemoryAccess(
        actor_id="agent",
        scopes=frozenset({MemoryScope.GLOBAL}),
        max_sensitivity=Sensitivity.PUBLIC,
    )

    assert memory.search((1, 0), access) == ()
