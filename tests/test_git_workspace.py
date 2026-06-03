import subprocess
import tempfile
import unittest
from pathlib import Path

from anubis.workspace import GitWorkspace, GitWorkspaceConfig


class GitWorkspaceTest(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "anubis@example.test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Anubis Test"], cwd=root, check=True)
        (root / "README.md").write_text("# Test\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "chore: initial"], cwd=root, check=True, capture_output=True, text=True)
        return directory, root

    def workspace(self, root: Path) -> GitWorkspace:
        return GitWorkspace(root, config=GitWorkspaceConfig(root=root.parent, timeout_seconds=5))

    def test_status_reports_branch_and_changes(self) -> None:
        directory, root = self.make_repo()
        with directory:
            (root / "README.md").write_text("# Test\n\nChanged\n", encoding="utf-8")

            status = self.workspace(root).status()

            self.assertEqual(status.branch, "main")
            self.assertFalse(status.clean)
            self.assertEqual(status.changes[0].path, "README.md")
            self.assertEqual(status.changes[0].status, "modified")

    def test_create_branch_generates_native_branch(self) -> None:
        directory, root = self.make_repo()
        with directory:
            result = self.workspace(root).create_branch("Feature Login")

            self.assertTrue(result.success)
            self.assertEqual(result.branch, "feature-login")
            self.assertEqual(self.workspace(root).status().branch, "feature-login")

    def test_diff_view_parses_files_hunks_and_counts(self) -> None:
        directory, root = self.make_repo()
        with directory:
            (root / "README.md").write_text("# Test\n\nChanged\n", encoding="utf-8")

            diff = self.workspace(root).diff()

            self.assertEqual(diff.files[0].path, "README.md")
            self.assertEqual(diff.files[0].additions, 2)
            self.assertEqual(diff.files[0].deletions, 0)
            self.assertTrue(diff.files[0].hunks)

    def test_generate_commit_and_commit_changes(self) -> None:
        directory, root = self.make_repo()
        with directory:
            (root / "feature.py").write_text("print('hello')\n", encoding="utf-8")
            workspace = self.workspace(root)

            proposal = workspace.generate_commit(description="add feature module", paths=("feature.py",), kind="feat", scope="core")
            result = workspace.commit(proposal)

            self.assertEqual(proposal.message, "feat(core): add feature module")
            self.assertTrue(result.success)
            self.assertIsNotNone(result.commit_sha)
            self.assertTrue(workspace.status().clean)

    def test_prepare_pr_draft_uses_current_branch_diff_and_risks(self) -> None:
        directory, root = self.make_repo()
        with directory:
            workspace = self.workspace(root)
            workspace.create_branch("anubis/task/git-panel")
            (root / "package.json").write_text('{"scripts": {}}\n', encoding="utf-8")

            draft = workspace.prepare_pr(description="Add native Git panel", linked_tasks=("task-001",))

            self.assertEqual(draft.head_branch, "anubis/task/git-panel")
            self.assertEqual(draft.base_branch, "main")
            self.assertIn("package.json", draft.changed_files)
            self.assertTrue(draft.risks)
            self.assertIn("task-001", draft.body)


if __name__ == "__main__":
    unittest.main()
