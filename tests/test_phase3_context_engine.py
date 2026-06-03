import tempfile
import unittest
from pathlib import Path

from backend.context import ContextEngine, ContextRetriever, RepositoryIndexer


class Phase3ContextEngineTest(unittest.TestCase):
    def test_indexes_retrieves_and_compresses_task_relevant_repo_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "agent").mkdir()
            (root / "agent" / "loop.py").write_text(
                "class AgentLoop:\n"
                "    def run(self, task):\n"
                "        context = get_context(task)\n"
                "        plan = planner.plan(task, context)\n",
                encoding="utf-8",
            )
            (root / "frontend.tsx").write_text("export const View = () => null\n", encoding="utf-8")
            index_path = root / "state" / "repo_context_index.jsonl"

            engine = ContextEngine(root=root, index_path=index_path)
            stats = engine.index_repository()
            chunks = engine.retrieve("agent loop planner context", top_k=2)
            compressed = engine.context_for_task("agent loop planner context", top_k=2)

            self.assertGreaterEqual(stats.files_indexed, 2)
            self.assertGreaterEqual(stats.chunks_indexed, 2)
            self.assertTrue(index_path.exists())
            self.assertEqual(chunks[0].path, "agent/loop.py")
            self.assertIn("agent/loop.py", compressed.text)
            self.assertLessEqual(len(compressed.text), compressed.token_budget_chars)

    def test_retriever_streams_top_k_from_existing_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("def alpha_context():\n    return 'planner loop'\n", encoding="utf-8")
            (root / "b.py").write_text("def beta_view():\n    return 'frontend display'\n", encoding="utf-8")
            index_path = root / "state" / "repo_context_index.jsonl"

            RepositoryIndexer(root=root, index_path=index_path).index()
            retriever = ContextRetriever(root=root, index_path=index_path)
            chunks = retriever.retrieve("planner loop", top_k=1)

            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].path, "a.py")


if __name__ == "__main__":
    unittest.main()
