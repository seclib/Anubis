from __future__ import annotations

from anubis import (
    HashingEmbedder,
    MemoryAccess,
    MemoryRecord,
    MemoryScope,
    QueryRoute,
    QueryRouter,
    RetrievalQuery,
    Sensitivity,
    SharedMemory,
    SharedMemoryVectorDB,
)


def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    first = HashingEmbedder(dimensions=8).embed("Suspicious login login")
    second = HashingEmbedder(dimensions=8).embed("Suspicious login login")

    assert first.vector == second.vector
    assert round(sum(value * value for value in first.vector), 6) == 1.0


def test_query_router_indexes_and_routes_scoped_results() -> None:
    memory = SharedMemory()
    router = QueryRouter(scoped_db=SharedMemoryVectorDB(memory))
    router.index(
        MemoryRecord(
            id="mem_login",
            content="suspicious login from rare location",
            scope=MemoryScope.SWARM,
            scope_id="swarm-1",
            owner_id="agent",
            sensitivity=Sensitivity.INTERNAL,
        )
    )

    response = router.query(
        RetrievalQuery(
            text="rare login",
            access=MemoryAccess(
                actor_id="agent",
                scopes=frozenset({MemoryScope.SWARM}),
                scope_ids=frozenset({"swarm-1"}),
                max_sensitivity=Sensitivity.INTERNAL,
            ),
            route=QueryRoute.SCOPED,
        )
    )

    assert response.results[0].record.id == "mem_login"
    assert response.results[0].route == QueryRoute.SCOPED


def test_query_router_filters_by_memory_isolation() -> None:
    memory = SharedMemory()
    router = QueryRouter(scoped_db=SharedMemoryVectorDB(memory))
    router.index(
        MemoryRecord(
            id="mem_secret",
            content="secret incident timeline",
            scope=MemoryScope.SWARM,
            scope_id="swarm-1",
            owner_id="agent",
            sensitivity=Sensitivity.SECRET,
        )
    )

    response = router.query(
        RetrievalQuery(
            text="incident timeline",
            access=MemoryAccess(
                actor_id="agent",
                scopes=frozenset({MemoryScope.SWARM}),
                scope_ids=frozenset({"swarm-1"}),
                max_sensitivity=Sensitivity.INTERNAL,
            ),
        )
    )

    assert response.results == ()


def test_hybrid_query_merges_scoped_and_global_results() -> None:
    scoped_memory = SharedMemory()
    global_memory = SharedMemory()
    router = QueryRouter(
        scoped_db=SharedMemoryVectorDB(scoped_memory),
        global_db=SharedMemoryVectorDB(global_memory),
    )
    router.index(
        MemoryRecord(
            id="mem_scoped",
            content="local containment playbook",
            scope=MemoryScope.SWARM,
            scope_id="swarm-1",
            owner_id="agent",
        )
    )
    router.index(
        MemoryRecord(
            id="mem_global",
            content="global containment policy",
            scope=MemoryScope.GLOBAL,
            scope_id="global",
            owner_id="system",
        ),
        db=QueryRoute.GLOBAL,
    )

    response = router.query(
        RetrievalQuery(
            text="containment",
            access=MemoryAccess(
                actor_id="agent",
                scopes=frozenset({MemoryScope.SWARM, MemoryScope.GLOBAL}),
                scope_ids=frozenset({"swarm-1"}),
            ),
            route=QueryRoute.HYBRID,
            limit=5,
        )
    )

    assert {result.record.id for result in response.results} == {"mem_scoped", "mem_global"}
    assert {result.route for result in response.results} == {QueryRoute.SCOPED, QueryRoute.GLOBAL}


def test_vector_db_syncs_from_shared_memory_vector_log() -> None:
    source_memory = SharedMemory()
    target_memory = SharedMemory()
    source_db = SharedMemoryVectorDB(source_memory)
    target_db = SharedMemoryVectorDB(target_memory)
    record = MemoryRecord(
        id="mem_a",
        content="malware hash indicator",
        scope=MemoryScope.GLOBAL,
        scope_id="global",
        owner_id="system",
        sensitivity=Sensitivity.PUBLIC,
    )
    target_memory.put(record)
    source_db.upsert(record, HashingEmbedder().embed(record.content))

    applied = target_db.sync_from_memory(source_memory)
    response = QueryRouter(scoped_db=target_db).query(
        RetrievalQuery(
            text="malware hash",
            access=MemoryAccess(
                actor_id="system",
                scopes=frozenset({MemoryScope.GLOBAL}),
                max_sensitivity=Sensitivity.PUBLIC,
            ),
            route=QueryRoute.SCOPED,
        )
    )

    assert applied == 1
    assert response.results[0].record.id == "mem_a"

