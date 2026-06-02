import tempfile
from pathlib import Path
import unittest

from backend.rag.obsidian_memory import (
    HashEmbeddingPipeline,
    MarkdownChunker,
    ObsidianMemoryRag,
    ObsidianVaultScanner,
    retrieve_from_obsidian,
)


class ObsidianMemoryRagTest(unittest.TestCase):
    def test_scans_chunks_embeds_and_retrieves_markdown_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "security.md").write_text(
                """---
title: Firewall Playbook
tags: [security, hardening]
---
# Firewall Rules

Use deny-by-default inbound policy and allow SSH only from trusted admin ranges.

## Validation

Audit firewall logs before opening new ports.
""",
                encoding="utf-8",
            )
            (vault / "journal.md").write_text(
                "# Garden Notes\n\nTomatoes need morning light and steady watering.\n",
                encoding="utf-8",
            )
            (vault / ".obsidian" / "workspace.md").parent.mkdir()
            (vault / ".obsidian" / "workspace.md").write_text("ignored editor state", encoding="utf-8")

            rag = ObsidianMemoryRag(vault)
            stats = rag.ingest()
            results = rag.retrieve("how should firewall ssh access be hardened", limit=2)

            self.assertEqual(stats["notes"], 2)
            self.assertGreaterEqual(stats["chunks"], 2)
            self.assertEqual(results[0]["path"], "security.md")
            self.assertIn("Firewall", results[0]["heading"])
            self.assertIn("hardening", results[0]["tags"])

    def test_tag_filter_limits_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "one.md").write_text("# One\n\nIncident response checklist. #security\n", encoding="utf-8")
            (vault / "two.md").write_text("# Two\n\nIncident response for garden watering. #garden\n", encoding="utf-8")

            rag = ObsidianMemoryRag(vault)
            rag.ingest()
            results = rag.retrieve("incident response", tags=["security"])

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["path"], "one.md")

    def test_convenience_retrieval_builds_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "memory.md").write_text("# Memory\n\nAnubis stores durable memory in markdown notes.\n", encoding="utf-8")

            results = retrieve_from_obsidian(vault, "where does Anubis store durable memory", limit=1)

            self.assertEqual(results[0]["path"], "memory.md")

    def test_embedding_is_deterministic(self) -> None:
        embedder = HashEmbeddingPipeline(dimensions=32)

        self.assertEqual(embedder.embed("same text"), embedder.embed("same text"))
        self.assertNotEqual(embedder.embed("same text"), embedder.embed("different text"))

    def test_chunker_splits_large_sections(self) -> None:
        scanner = ObsidianVaultScanner(Path("/tmp/nonexistent"))
        note = scanner.scan()
        self.assertEqual(note, [])

        from backend.rag.obsidian_memory import ObsidianNote

        chunker = MarkdownChunker(chunk_chars=240, overlap=40)
        big_note = ObsidianNote(
            path="large.md",
            title="Large",
            content="# Large\n\n" + "alpha beta gamma " * 80,
        )

        chunks = chunker.chunk(big_note)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.note_path == "large.md" for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
