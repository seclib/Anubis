import tempfile
import unittest
from pathlib import Path

from anubis.memory import MemoryCollection
from anubis.workspace import VaultWorkspace, VaultWorkspaceError


class VaultWorkspaceTest(unittest.TestCase):
    def make_vault(self) -> tuple[tempfile.TemporaryDirectory[str], Path, VaultWorkspace]:
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        (root / "Architecture.md").write_text(
            "# Architecture\n\n#systems\n\nSee [[Memory]] and [Planner](Planner.md).\n",
            encoding="utf-8",
        )
        (root / "Memory.md").write_text(
            "# Memory\n\nLocal-first vector recall for vault notes.\n",
            encoding="utf-8",
        )
        (root / "Planner.md").write_text(
            "# Planner\n\nAtomic planning steps.\n",
            encoding="utf-8",
        )
        return directory, root, VaultWorkspace(root)

    def test_navigation_extracts_markdown_metadata(self) -> None:
        directory, _root, workspace = self.make_vault()
        with directory:
            notes = {note.path: note for note in workspace.list_notes()}

            self.assertIn("Architecture.md", notes)
            self.assertEqual(notes["Architecture.md"].title, "Architecture")
            self.assertEqual(notes["Architecture.md"].tags, ("systems",))
            self.assertEqual(notes["Architecture.md"].links, ("Memory", "Planner.md"))

    def test_backlinks_detect_wikilinks_and_markdown_links(self) -> None:
        directory, _root, workspace = self.make_vault()
        with directory:
            memory_backlinks = workspace.backlinks("Memory.md")
            planner_backlinks = workspace.backlinks("Planner.md")

            self.assertEqual(memory_backlinks[0].source_path, "Architecture.md")
            self.assertIn("Memory", memory_backlinks[0].excerpt)
            self.assertEqual(planner_backlinks[0].source_path, "Architecture.md")

    def test_graph_resolves_edges_between_notes(self) -> None:
        directory, _root, workspace = self.make_vault()
        with directory:
            graph = workspace.graph()
            edges = {(edge.source, edge.target) for edge in graph.edges}

            self.assertEqual({node.id for node in graph.nodes}, {"Architecture.md", "Memory.md", "Planner.md"})
            self.assertIn(("Architecture.md", "Memory.md"), edges)
            self.assertIn(("Architecture.md", "Planner.md"), edges)

    def test_search_combines_local_and_memory_results(self) -> None:
        directory, _root, workspace = self.make_vault()
        with directory:
            workspace.index_all()
            workspace.memory.remember(
                MemoryCollection.DOCS,
                "# Release Notes\n\nGraph view and backlinks shipped.",
                source="Release.md",
                metadata={"path": "Release.md", "title": "Release Notes"},
            )

            results = workspace.search("graph backlinks", limit=5)

            self.assertEqual(results[0].path, "Release.md")
            self.assertEqual(results[0].source, "memory")
            self.assertTrue(any(result.path == "Architecture.md" for result in results))

    def test_write_indexes_note_and_blocks_path_escape(self) -> None:
        directory, _root, workspace = self.make_vault()
        with directory:
            result = workspace.write_note("Research/Search.md", "# Search\n\nAI-assisted search.", index=True)
            search_results = workspace.search("AI-assisted", limit=3)

            self.assertEqual(result.path, "Research/Search.md")
            self.assertTrue(result.indexed)
            self.assertTrue(any(item.path == "Research/Search.md" for item in search_results))
            with self.assertRaises(VaultWorkspaceError):
                workspace.read_note("../secret.md")


if __name__ == "__main__":
    unittest.main()
