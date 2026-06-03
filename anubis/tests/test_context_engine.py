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


if __name__ == "__main__":
    unittest.main()
