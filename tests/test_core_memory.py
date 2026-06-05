from __future__ import annotations

from core.memory import (
    EpisodicMemory,
    HashingEmbedder,
    InMemoryVectorStore,
    MemoryManager,
    RetrievalNamespace,
    SemanticMemory,
)


def test_episodic_memory_is_append_only_execution_log() -> None:
    memory = EpisodicMemory()

    first = memory.append(
        event_type="task.started",
        actor="orchestrator",
        summary="Task started",
        payload={"task_id": "task_1"},
    )
    second = memory.append(
        event_type="task.succeeded",
        actor="executor_agent",
        summary="Task succeeded",
        payload={"task_id": "task_1"},
    )

    assert first.record_id == "episode_00000001"
    assert second.record_id == "episode_00000002"
    assert [record.event_type for record in memory.all()] == [
        "task.started",
        "task.succeeded",
    ]
    assert memory.recent(1) == (second,)


def test_semantic_memory_versions_facts_without_overwrite() -> None:
    memory = SemanticMemory()

    first = memory.append_fact(
        subject="sandbox",
        predicate="network",
        value="disabled",
        source="policy",
    )
    second = memory.append_fact(
        subject="sandbox",
        predicate="network",
        value="disabled_by_default",
        source="policy",
        supersedes=first.record_id,
    )

    assert first.record_id == "semantic_00000001"
    assert second.record_id == "semantic_00000002"
    assert memory.history("sandbox", "network") == (first, second)
    assert memory.latest("sandbox", "network") == second
    assert memory.get(first.record_id) == first


def test_vector_store_appends_duplicate_document_ids_without_overwrite() -> None:
    embedder = HashingEmbedder(dimensions=16)
    store = InMemoryVectorStore()

    first_embedding = embedder.embed("alpha detection")
    second_embedding = embedder.embed("alpha detection updated")
    first = store.append(document_id="doc_alpha", text="alpha detection", embedding=first_embedding)
    second = store.append(
        document_id="doc_alpha",
        text="alpha detection updated",
        embedding=second_embedding,
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert [document.text for document in store.all()] == [
        "alpha detection",
        "alpha detection updated",
    ]


def test_retrieval_is_deterministic_and_namespace_filtered() -> None:
    manager = MemoryManager()
    manager.append_fact(subject="sandbox", predicate="network", value="disabled", source="policy")
    manager.append_fact(subject="agents", predicate="state", value="stateless workers", source="spec")
    manager.append_episode(
        event_type="task.failed",
        actor="executor_agent",
        summary="Sandbox denied unsafe operation",
        index=True,
    )

    first = manager.retrieve(
        "sandbox network",
        namespace=RetrievalNamespace.SEMANTIC,
        limit=2,
    )
    second = manager.retrieve(
        "sandbox network",
        namespace=RetrievalNamespace.SEMANTIC,
        limit=2,
    )

    assert [result.document.document_id for result in first.results] == [
        result.document.document_id for result in second.results
    ]
    assert all(
        result.document.metadata["namespace"] == RetrievalNamespace.SEMANTIC
        for result in first.results
    )
    assert first.results[0].document.metadata["record_id"] == "semantic_00000001"


def test_memory_manager_snapshot_counts_append_only_records() -> None:
    manager = MemoryManager()

    manager.append_episode(event_type="loop.started", actor="brain", summary="Loop started")
    manager.append_fact(subject="anubis", predicate="mode", value="local-first")

    assert manager.snapshot() == {
        "episodic_count": 1,
        "semantic_count": 1,
        "vector_count": 1,
        "append_only": True,
    }
