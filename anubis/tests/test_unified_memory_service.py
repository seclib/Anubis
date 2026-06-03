import tempfile
import unittest
from pathlib import Path

from anubis.memory import (
    InMemoryMemoryStore,
    MemoryCollection,
    MemoryMigrationStrategy,
    UnifiedMemoryService,
)


class UnifiedMemoryServiceTest(unittest.TestCase):
    def test_retrieves_across_repo_docs_and_conversations(self) -> None:
        service = UnifiedMemoryService()
        service.remember(
            MemoryCollection.REPO,
            "The scheduler executes DAG nodes when dependencies are satisfied.",
            source="repo:anubis/distributed/scheduler.py",
        )
        service.remember(
            MemoryCollection.DOCS,
            "Architecture notes: DAG execution allows parallel software tasks.",
            source="docs:architecture.md",
        )
        service.remember(
            MemoryCollection.CONVERSATIONS,
            "User asked for a dependency based task graph engine.",
            source="conversation:task-graph",
        )

        results = service.retrieve("DAG execution task graph dependencies", limit=3, min_score=0.01)

        self.assertEqual(len(results), 3)
        self.assertEqual(
            {result.record.collection for result in results},
            {MemoryCollection.REPO, MemoryCollection.DOCS, MemoryCollection.CONVERSATIONS},
        )
        self.assertTrue(all(result.score > 0 for result in results))

    def test_deduplicates_identical_content_per_collection(self) -> None:
        service = UnifiedMemoryService()

        first = service.remember(MemoryCollection.DOCS, "Repeatable memory fact.", source="docs:first")
        second = service.remember(MemoryCollection.DOCS, "  repeatable   memory fact.  ", source="docs:second")
        third = service.remember(MemoryCollection.REPO, "Repeatable memory fact.", source="repo:first")

        self.assertEqual(first.inserted, 1)
        self.assertEqual(second.deduplicated, 1)
        self.assertEqual(third.inserted, 1)
        self.assertEqual(len(service.retrieve("repeatable memory fact", limit=5)), 2)

    def test_lazy_loads_only_touched_collections(self) -> None:
        store = InMemoryMemoryStore()
        service = UnifiedMemoryService(store=store)

        self.assertEqual(service.loaded_collections, ())
        service.remember(MemoryCollection.CONVERSATIONS, "Planner chose a minimal context budget.", source="conversation:1")

        self.assertEqual(service.loaded_collections, (MemoryCollection.CONVERSATIONS,))
        self.assertEqual(store.loaded_collections, {MemoryCollection.CONVERSATIONS})

    def test_migration_strategy_routes_sources_to_target_collections(self) -> None:
        service = UnifiedMemoryService()
        migration = MemoryMigrationStrategy(service)

        repo_result = migration.migrate_repo_memory(
            [{"path": "anubis/context/builder.py", "content": "Context builder ranks files for LLM context."}]
        )
        docs_result = migration.migrate_obsidian_notes(
            [{"path": "Architecture/Memory.md", "content": "Unified memory stores Obsidian docs in Qdrant."}]
        )
        conversation_result = migration.migrate_conversation_memory(
            [{"conversation_id": "c1", "role": "user", "content": "Remember context budget decisions."}]
        )

        self.assertEqual(repo_result.inserted, 1)
        self.assertEqual(docs_result.inserted, 1)
        self.assertEqual(conversation_result.inserted, 1)
        self.assertEqual(
            {result.record.collection for result in service.retrieve("context memory budget qdrant", limit=5)},
            {MemoryCollection.REPO, MemoryCollection.DOCS, MemoryCollection.CONVERSATIONS},
        )

    def test_migration_strategy_can_read_obsidian_paths_without_deleting_source(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            note = Path(directory) / "Memory.md"
            note.write_text("# Memory\n\nUnified memory keeps source notes intact.", encoding="utf-8")
            service = UnifiedMemoryService()

            result = MemoryMigrationStrategy(service).migrate_obsidian_notes([note])

            self.assertEqual(result.inserted, 1)
            self.assertTrue(note.exists())
            self.assertEqual(service.retrieve("source notes intact", collections=["docs"], limit=1)[0].record.source, note.as_posix())

    def test_plan_documents_safe_append_only_migration(self) -> None:
        plan = MemoryMigrationStrategy(UnifiedMemoryService()).plan()

        self.assertEqual(plan.collections, (MemoryCollection.REPO, MemoryCollection.DOCS, MemoryCollection.CONVERSATIONS))
        self.assertTrue(any("append-only" in check for check in plan.safety_checks))
        self.assertTrue(any("legacy" in step for step in plan.steps))


if __name__ == "__main__":
    unittest.main()
