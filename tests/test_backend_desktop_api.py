import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.routes import brain, desktop, local, notes, rag, skills
from backend.main import app
from backend.vault.service import VaultService


class BackendDesktopApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_path = Path(self.temp_dir.name)
        self.vault = VaultService(self.vault_path)
        local.reset_route_state()
        notes.reset_route_state()
        rag.reset_route_state()
        desktop.reset_route_state()
        skills.reset_route_state()
        brain.reset_route_state()
        self.patchers = [
            patch("backend.api.routes.local.get_vault", return_value=self.vault),
            patch("backend.api.routes.notes.get_vault", return_value=self.vault),
            patch("backend.api.routes.notes._index_all"),
            patch("backend.api.routes.desktop.get_vault", return_value=self.vault),
            patch("backend.api.routes.skills.get_skills_dir", return_value=self.vault_path / "skills"),
            patch("backend.api.routes.brain._vault", return_value=self.vault),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client = TestClient(
            app,
            base_url="http://127.0.0.1",
            client=("127.0.0.1", 50000),
        )

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def test_notes_write_read_and_path_escape_guard(self) -> None:
        write_response = self.client.put(
            "/notes",
            json={"path": "notes/example.md", "content": "# Example\n\nDurable knowledge."},
        )
        self.assertEqual(write_response.status_code, 200)

        read_response = self.client.get("/notes/notes/example.md")
        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()["content"], "# Example\n\nDurable knowledge.")

        escape_response = self.client.post("/read", json={"file": "../secret.md"})
        self.assertEqual(escape_response.status_code, 400)

    def test_local_write_can_skip_reindex_for_fast_desktop_edits(self) -> None:
        with patch("backend.api.routes.local.get_indexer") as get_indexer:
            response = self.client.post(
                "/write",
                json={
                    "file": "notes/draft.md",
                    "content": "# Draft\n\nFast local edit.",
                    "index": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["indexed_chunks"], None)
        get_indexer.assert_not_called()
        self.assertEqual(self.vault.read_note("notes/draft.md"), "# Draft\n\nFast local edit.")

    def test_health_ready_reports_runtime_configuration(self) -> None:
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ready")
        self.assertIn("qdrant_collection", payload)

    def test_skill_graph_api_exposes_skills_edges_and_markdown(self) -> None:
        skills_dir = self.vault_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "memory_skill.md").write_text(
            "---\nname: memory_skill\nobjective: Preserve state.\n---\n# Memory Skill\n",
            encoding="utf-8",
        )
        (skills_dir / "retrieval_skill.md").write_text(
            "---\nname: retrieval_skill\ndependencies:\n  - memory_skill\n---\n# Retrieval Skill\n",
            encoding="utf-8",
        )

        graph_response = self.client.get("/api/skill-graph")
        self.assertEqual(graph_response.status_code, 200)
        graph = graph_response.json()
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertTrue(any(node["id"] == "retrieval_skill" for node in graph["nodes"]))
        self.assertTrue(any(edge["type"] == "depends_on" for edge in graph["edges"]))
        self.assertTrue(any("Retrieval Skill" in node.get("markdown", "") for node in graph["nodes"]))

        skills_response = self.client.get("/api/skills")
        self.assertEqual(skills_response.status_code, 200)
        self.assertEqual({node["type"] for node in skills_response.json()}, {"skill"})

    def test_brain_snapshot_exposes_dashboard_foundation(self) -> None:
        self.vault.write_note("notes/dashboard.md", "# Dashboard\n\nObserve the system.")
        response = self.client.get("/brain/snapshot")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("system_health", payload)
        self.assertIn("memory", payload)
        self.assertIn("agent_activity", payload)
        self.assertIn("architecture", payload)
        self.assertEqual(payload["memory"]["notes"], 1)
        self.assertGreaterEqual(payload["memory"]["chunks"], 1)
        self.assertIn("backend", payload["system_health"])
        self.assertTrue(payload["agent_activity"]["active_agents"])
        self.assertEqual(payload["architecture"]["live_updates"], "WebSocket /brain/ws")

    def test_desktop_mvp_hides_internal_ai_surface(self) -> None:
        with patch("backend.api.routes.desktop._index_all"):
            ingest_response = self.client.post(
                "/library/ingest",
                json={"name": "Roadmap.txt", "content": "Ship a calm notes workspace."},
            )

        self.assertEqual(ingest_response.status_code, 200)
        self.assertEqual(ingest_response.json()["path"], "library/Roadmap.md")

        library_response = self.client.get("/library")
        self.assertEqual(library_response.status_code, 200)
        self.assertEqual(library_response.json()["items"][0]["title"], "Roadmap")

        retriever = type(
            "Retriever",
            (),
            {
                "search": lambda _self, _query, _limit: [
                    {
                        "path": "library/Roadmap.md",
                        "heading": "Roadmap",
                        "text": "Ship a calm notes workspace.",
                        "score": 0.92,
                    }
                ]
            },
        )()
        with patch("backend.api.routes.desktop.get_retriever", return_value=retriever):
            search_response = self.client.post("/search", json={"query": "workspace"})

        self.assertEqual(search_response.status_code, 200)
        search_payload = search_response.json()
        self.assertEqual(search_payload["results"][0]["title"], "Roadmap")
        self.assertNotIn("rag", str(search_payload).lower())

        agent = type(
            "Agent",
            (),
            {
                "chat": lambda _self, _message: {
                    "answer": "Use the roadmap note.",
                    "chunks_used": [{"path": "library/Roadmap.md", "heading": "Roadmap", "text": "Ship a calm notes workspace."}],
                }
            },
        )()
        with patch("backend.api.routes.desktop.get_agent", return_value=agent):
            assistant_response = self.client.post("/assistant/chat", json={"message": "What should I ship?"})

        self.assertEqual(assistant_response.status_code, 200)
        assistant_payload = assistant_response.json()
        self.assertEqual(assistant_payload["answer"], "Use the roadmap note.")
        self.assertNotIn("agent", str(assistant_payload).lower())
        self.assertNotIn("embedding", str(assistant_payload).lower())


if __name__ == "__main__":
    unittest.main()
