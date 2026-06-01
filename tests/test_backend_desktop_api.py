import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.routes import local, notes, rag
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
        self.patchers = [
            patch("backend.api.routes.local.get_vault", return_value=self.vault),
            patch("backend.api.routes.notes.get_vault", return_value=self.vault),
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


if __name__ == "__main__":
    unittest.main()
