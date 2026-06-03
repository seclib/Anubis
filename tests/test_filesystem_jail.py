import json
import os
import tempfile
import unittest
from pathlib import Path

from anubis.distributed import (
    FileAccessDecision,
    FilesystemJail,
    FilesystemJailConfig,
    FilesystemJailViolation,
)


class FilesystemJailTest(unittest.TestCase):
    def jail(self, root: str) -> FilesystemJail:
        return FilesystemJail(FilesystemJailConfig(root_dir=root))

    def test_virtual_workspace_is_isolated_per_task(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            jail = self.jail(root)

            alpha = jail.create_workspace("alpha")
            beta = jail.create_workspace("beta")

            self.assertEqual(alpha.virtual_root, "/workspace/alpha")
            self.assertEqual(beta.virtual_root, "/workspace/beta")
            self.assertNotEqual(alpha.real_root, beta.real_root)
            self.assertTrue(alpha.real_root.exists())
            self.assertTrue(str(alpha.real_root).startswith(str(Path(root).resolve())))

    def test_allows_only_assigned_workspace_read_write(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            jail = self.jail(root)

            real_path = jail.write_file("task-001", "/workspace/task-001/src/app.py", "print('ok')")
            content = jail.read_file("task-001", "/workspace/task-001/src/app.py")

            self.assertEqual(content, "print('ok')")
            self.assertTrue(real_path.exists())
            self.assertTrue(str(real_path).startswith(str(jail.workspace_for("task-001").real_root)))
            self.assertEqual([entry.decision for entry in jail.audit_entries()], [FileAccessDecision.ALLOW, FileAccessDecision.ALLOW])

    def test_blocks_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            jail = self.jail(root)

            with self.assertRaises(FilesystemJailViolation):
                jail.read_file("task-001", "/workspace/task-001/../secret.txt")

            self.assertEqual(jail.audit_entries()[0].decision, FileAccessDecision.DENY)
            self.assertIn("traversal", jail.audit_entries()[0].reason)

    def test_blocks_absolute_system_and_cross_task_paths(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            jail = self.jail(root)

            for path in ("/etc/passwd", "/tmp/host.txt", "/workspace/other/file.txt", "relative/file.txt"):
                with self.assertRaises(FilesystemJailViolation):
                    jail.read_file("task-001", path)

            self.assertEqual(len(jail.audit_entries()), 4)
            self.assertTrue(all(entry.decision == FileAccessDecision.DENY for entry in jail.audit_entries()))

    @unittest.skipIf(not hasattr(os, "symlink"), "symlink not available")
    def test_blocks_symlink_escape_from_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            jail = self.jail(root)
            workspace = jail.create_workspace("task-001")
            outside = Path(root) / "outside.txt"
            outside.write_text("host secret", encoding="utf-8")
            (workspace.real_root / "leak").symlink_to(outside)

            with self.assertRaises(FilesystemJailViolation):
                jail.read_file("task-001", "/workspace/task-001/leak")

            self.assertEqual(jail.audit_entries()[0].decision, FileAccessDecision.DENY)
            self.assertIn("escapes", jail.audit_entries()[0].reason)

    def test_audit_logging_records_allowed_and_denied_attempts_to_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            audit_path = Path(root) / "audit" / "filesystem.jsonl"
            jail = FilesystemJail(FilesystemJailConfig(root_dir=root, audit_log_path=str(audit_path)))

            jail.write_file("task-001", "/workspace/task-001/file.txt", "safe")
            with self.assertRaises(FilesystemJailViolation):
                jail.write_file("task-001", "/workspace/task-001/../../escape.txt", "blocked")

            lines = audit_path.read_text(encoding="utf-8").splitlines()
            records = [json.loads(line) for line in lines]
            self.assertEqual([record["decision"] for record in records], ["allow", "deny"])
            self.assertEqual(records[0]["action"], "write")
            self.assertEqual(records[1]["action"], "write")
            self.assertIn("traversal", records[1]["reason"])


if __name__ == "__main__":
    unittest.main()
