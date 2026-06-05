import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from anubis.context.builder import ContextBuilder
from anubis.context.chunker import CodeChunker
from anubis.context.compressor.compressor import ContextCompressor
from anubis.context.indexer.indexer import RepositoryIndexer
from anubis.context.retriever.retriever import HybridContextRetriever
from anubis.context.scanner import RepositoryScanner
from anubis.context.service import ContextBuilderService
from anubis.context.schema import ContextBudget, ContextBuildRequest


class AdvancedContextEngineTest(unittest.TestCase):
    def test_repository_indexing_extracts_metadata_and_symbols(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            root = Path(directory)
            (root / "service.py").write_text(
                "import os\n\n"
                "class PaymentService:\n"
                "    def charge_customer(self, amount):\n"
                "        return amount\n\n"
                "def helper():\n"
                "    return 'ok'\n",
                encoding="utf-8",
            )

            files = RepositoryScanner(root).scan()
            index = RepositoryIndexer(root).index_repository()

            self.assertEqual(files[0].language, "python")
            self.assertIn("PaymentService", files[0].symbols)
            self.assertIn("helper", files[0].symbols)
            self.assertGreaterEqual(len(index.chunks), 2)
            self.assertTrue(all(chunk.embedding for chunk in index.chunks))

    def test_chunker_creates_function_and_class_aware_chunks(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            root = Path(directory)
            file_path = root / "ui.ts"
            file_path.write_text(
                "export class CommandPalette {}\n\n"
                "export function openCommandPalette() {\n"
                "  return true\n"
                "}\n",
                encoding="utf-8",
            )
            metadata = RepositoryScanner(root).scan()[0]

            chunks = CodeChunker(root).chunk_file(metadata)

            symbols = {symbol for chunk in chunks for symbol in chunk.symbols}
            self.assertIn("CommandPalette", symbols)
            self.assertIn("openCommandPalette", symbols)

    def test_hybrid_retrieval_ranks_symbol_and_keyword_relevance(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            root = Path(directory)
            (root / "payments.py").write_text(
                "class PaymentService:\n"
                "    def refund_customer(self, payment_id):\n"
                "        return payment_id\n",
                encoding="utf-8",
            )
            (root / "theme.py").write_text(
                "def render_theme():\n"
                "    return 'blue'\n",
                encoding="utf-8",
            )
            index = RepositoryIndexer(root).index_repository()

            results = HybridContextRetriever().retrieve(index, "fix PaymentService refund_customer bug", top_k=2)

            self.assertEqual(results[0].chunk.file_path, "payments.py")
            self.assertGreater(results[0].symbol_score, 0)
            self.assertGreaterEqual(results[0].score, results[-1].score)

    def test_context_compression_dedupes_and_respects_budget(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            root = Path(directory)
            (root / "large.py").write_text(
                "def target_function():\n"
                + "\n".join(f"    value_{index} = {index}" for index in range(120))
                + "\n    return value_1\n",
                encoding="utf-8",
            )
            index = RepositoryIndexer(root).index_repository()
            results = HybridContextRetriever().retrieve(index, "target_function value_1", top_k=5)

            chunks, summary = ContextCompressor(max_chars=700, per_chunk_chars=300).compress(
                "target_function value_1",
                results,
            )

            self.assertLessEqual(sum(len(str(chunk["content"])) for chunk in chunks), 700)
            self.assertIn("large.py", summary)

    def test_context_builder_outputs_required_json_shape(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            root = Path(directory)
            (root / "agent.py").write_text(
                "class AgentLoop:\n"
                "    def plan(self, task):\n"
                "        return task\n",
                encoding="utf-8",
            )

            built = ContextBuilder(root).build("AgentLoop plan task", top_k=3)
            payload = asdict(built)

            self.assertEqual(payload["task"], "AgentLoop plan task")
            self.assertIn("context_chunks", payload)
            self.assertIn("summary", payload)
            self.assertEqual(payload["context_chunks"][0]["file"], "agent.py")
            self.assertIn("score", payload["context_chunks"][0])

    def test_context_builder_returns_minimal_ranked_file_set(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            root = Path(directory)
            files = {
                "services/orchestrator/context_builder.py": "class ContextBuilder:\n    def rank_files(self):\n        return 'context budget ranking'\n",
                "services/orchestrator/repo_state.py": "def collect_repo_state():\n    return 'changed files open files context'\n",
                "services/memory/context_memory.py": "def load_context_memory():\n    return 'memory relevance context builder'\n",
                "services/planner/planning.py": "def plan_context_task():\n    return 'planner context steps'\n",
                "services/executor/execution.py": "def execute_context_task():\n    return 'executor context step'\n",
                "docs/theme.md": "frontend colors and dashboard layout\n",
            }
            for relative_path, content in files.items():
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            request = ContextBuildRequest(
                task="implement context builder file ranking token budget memory",
                repo_state={
                    "changed_files": ["services/orchestrator/context_builder.py"],
                    "open_files": ["services/memory/context_memory.py"],
                    "recent_files": ["services/orchestrator/repo_state.py"],
                },
                memory={
                    "facts": [
                        {"text": "Context builder must cap retrieved files and preserve relevant memory.", "source": "architecture"},
                        {"text": "Dashboard theme uses blue controls.", "source": "ui"},
                    ]
                },
                budget=ContextBudget(max_tokens=1200, max_files=5, min_files=3, max_chunks_per_file=1),
            )

            minimal = ContextBuilder(root).build_minimal(request)

            self.assertGreaterEqual(len(minimal.files), 3)
            self.assertLessEqual(len(minimal.files), 5)
            self.assertEqual(minimal.files[0].path, "services/orchestrator/context_builder.py")
            self.assertLessEqual(minimal.estimated_tokens, minimal.token_budget)
            self.assertIn("architecture", {item["source"] for item in minimal.memory})
            self.assertNotIn("docs/theme.md", [file.path for file in minimal.files])

    def test_context_builder_enforces_file_and_token_budget(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            root = Path(directory)
            repeated = "\n".join(
                f"def context_budget_helper_{index}():\n    return 'context builder ranking token budget {index}'"
                for index in range(80)
            )
            for index in range(8):
                (root / f"context_module_{index}.py").write_text(repeated, encoding="utf-8")

            minimal = ContextBuilder(root).build_minimal(
                "context builder ranking token budget",
                budget=ContextBudget(max_tokens=320, max_files=4, min_files=2, max_chunks_per_file=2),
            )

            self.assertLessEqual(len(minimal.files), 4)
            self.assertLessEqual(minimal.estimated_tokens, 320)
            self.assertLessEqual(len(minimal.context), 320 * 4)

    def test_context_builder_accepts_inline_repo_state_and_memory(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            root = Path(directory)
            (root / "reviewer.py").write_text(
                "class ReviewerAgent:\n"
                "    def validate_context(self):\n"
                "        return 'review context memory validation'\n",
                encoding="utf-8",
            )

            minimal = ContextBuilder(root).build_minimal(
                "reviewer context validation",
                repo_state={"changed_files": ["reviewer.py"]},
                memory={"recent": ["Reviewer memory should be included for context validation.", "Unrelated billing note."]},
                budget=ContextBudget(max_tokens=600, max_files=5, min_files=1),
            )

            self.assertEqual(minimal.files[0].path, "reviewer.py")
            self.assertIn("changed", minimal.files[0].reason)
            self.assertIn("path_match", minimal.files[0].reason)
            self.assertEqual(len(minimal.memory), 1)
            self.assertIn("Reviewer memory", minimal.memory[0]["text"])

    def test_context_builder_service_exposes_minimal_context_boundary(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            root = Path(directory)
            (root / "orchestrator.py").write_text(
                "class Orchestrator:\n"
                "    def build_context(self):\n"
                "        return 'minimal context for distributed agents'\n",
                encoding="utf-8",
            )

            minimal = ContextBuilderService(root).build_context(
                "orchestrator minimal context distributed agents",
                repo_state={"changed_files": ["orchestrator.py"]},
                budget=ContextBudget(max_tokens=500, max_files=3, min_files=1),
            )

            self.assertEqual(minimal.task, "orchestrator minimal context distributed agents")
            self.assertEqual(minimal.files[0].path, "orchestrator.py")
            self.assertLessEqual(len(minimal.files), 3)


if __name__ == "__main__":
    unittest.main()
