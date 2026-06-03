import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.api.routes import brain, desktop, local, notes, production, rag, skills, terminal, vault_workspace
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
        production.reset_route_state()
        desktop.reset_route_state()
        skills.reset_route_state()
        brain.reset_route_state()
        terminal.reset_route_state()
        vault_workspace.reset_route_state()
        self.patchers = [
            patch("backend.api.routes.local.get_vault", return_value=self.vault),
            patch("backend.api.routes.notes.get_vault", return_value=self.vault),
            patch("backend.api.routes.notes._index_all"),
            patch("backend.api.routes.desktop.get_vault", return_value=self.vault),
            patch("backend.api.routes.skills.get_skills_dir", return_value=self.vault_path / "skills"),
            patch("backend.api.routes.brain._vault", return_value=self.vault),
            patch("backend.api.routes.vault_workspace.get_vault_workspace", return_value=vault_workspace.VaultWorkspace(self.vault_path)),
            patch("backend.api.routes.production.get_indexer"),
            patch("backend.api.routes.production.get_retriever"),
        ]
        self.mocks = [patcher.start() for patcher in self.patchers]
        self.mocks[-2].return_value.reindex_all.return_value = 3
        self.mocks[-1].return_value.search.return_value = [
            {"path": "notes/context.md", "heading": "Context", "text": "Anubis remembers files first.", "score": 0.9}
        ]
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

    def test_production_contract_exposes_sync_memory_and_ask(self) -> None:
        sync_response = self.client.post("/sync")
        self.assertEqual(sync_response.status_code, 200)
        self.assertEqual(sync_response.json(), {"status": "indexed", "chunks": 3})

        memory_response = self.client.post("/memory", json={"query": "files first", "limit": 1})
        self.assertEqual(memory_response.status_code, 200)
        self.assertEqual(memory_response.json()["chunks"][0]["path"], "notes/context.md")

        agent_result = {
            "task": "Summarize Anubis",
            "accepted": True,
            "answer": "Anubis uses files first.",
            "memory_path": "agent-runs/test.md",
            "history": [],
        }
        with patch("backend.api.routes.production.AsyncAgentLoop") as loop_class:
            loop_class.return_value.run = AsyncMock(return_value=agent_result)
            ask_response = self.client.post("/ask", json={"task": "Summarize Anubis", "max_rounds": 2})

        self.assertEqual(ask_response.status_code, 200)
        self.assertEqual(ask_response.json()["answer"], "Anubis uses files first.")

    def test_terminal_api_runs_sandboxed_command_and_streams_events(self) -> None:
        create_response = self.client.post("/api/terminal/sessions", json={"task_id": "api-terminal"})
        self.assertEqual(create_response.status_code, 200)
        session = create_response.json()["session"]

        command_response = self.client.post(
            f"/api/terminal/sessions/{session['session_id']}/commands",
            json={"command": "echo terminal-ready"},
        )

        self.assertEqual(command_response.status_code, 200)
        command_payload = command_response.json()
        self.assertTrue(command_payload["command"]["success"])
        self.assertIn("terminal-ready", command_payload["command"]["output"])

        events_response = self.client.get(f"/api/terminal/sessions/{session['session_id']}/events")
        self.assertEqual(events_response.status_code, 200)
        event_types = [event["event_type"] for event in events_response.json()["events"]]
        self.assertIn("command_started", event_types)
        self.assertIn("output", event_types)
        self.assertIn("command_completed", event_types)

    def test_git_workspace_api_prepares_diff_commit_and_pr_payload(self) -> None:
        repo = self.vault_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "anubis@example.test"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Anubis Test"], cwd=repo, check=True)
        (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "chore: initial"], cwd=repo, check=True, capture_output=True, text=True)
        (repo / "README.md").write_text("# Repo\n\nNative Git workspace\n", encoding="utf-8")

        with patch("backend.api.routes.git_workspace.settings.project_root", self.vault_path):
            branch_response = self.client.post(
                "/api/git/branches",
                json={"repo_path": "repo", "branch": "Feature Git UX"},
            )
            diff_response = self.client.post("/api/git/diff", json={"repo_path": "repo"})
            proposal_response = self.client.post(
                "/api/git/commits/proposal",
                json={"repo_path": "repo", "description": "add native git workspace", "paths": ["README.md"]},
            )
            pr_response = self.client.post(
                "/api/git/pull-request/draft",
                json={"repo_path": "repo", "description": "add native git workspace", "linked_tasks": ["task-git"]},
            )

        self.assertEqual(branch_response.status_code, 200)
        self.assertEqual(branch_response.json()["branch"], "feature-git-ux")
        self.assertEqual(diff_response.status_code, 200)
        self.assertEqual(diff_response.json()["files"][0]["path"], "README.md")
        self.assertEqual(proposal_response.status_code, 200)
        self.assertEqual(proposal_response.json()["message"], "feat: add native git workspace")
        self.assertEqual(pr_response.status_code, 200)
        self.assertIn("task-git", pr_response.json()["body"])

    def test_vault_workspace_api_exposes_navigation_graph_backlinks_and_search(self) -> None:
        self.vault.write_note("Architecture.md", "# Architecture\n\nSee [[Memory]] and [Planner](Planner.md).")
        self.vault.write_note("Memory.md", "# Memory\n\nLocal-first memory search.")
        self.vault.write_note("Planner.md", "# Planner\n\nPlan execution.")

        navigation_response = self.client.get("/api/vault/navigation")
        graph_response = self.client.get("/api/vault/graph")
        backlinks_response = self.client.get("/api/vault/backlinks", params={"path": "Memory.md"})
        search_response = self.client.get("/api/vault/search", params={"query": "memory search"})

        self.assertEqual(navigation_response.status_code, 200)
        self.assertTrue(any(note["path"] == "Architecture.md" for note in navigation_response.json()["notes"]))
        self.assertEqual(graph_response.status_code, 200)
        edges = {(edge["source"], edge["target"]) for edge in graph_response.json()["edges"]}
        self.assertIn(("Architecture.md", "Memory.md"), edges)
        self.assertEqual(backlinks_response.status_code, 200)
        self.assertEqual(backlinks_response.json()["backlinks"][0]["source_path"], "Architecture.md")
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()["results"][0]["path"], "Memory.md")


if __name__ == "__main__":
    unittest.main()
