from __future__ import annotations

import os
import subprocess
import sys
import unittest

from cli.command_router import LEGACY_CLI_COMMANDS, UnifiedCommandRouter


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


class CliPhase1UnificationTest(unittest.TestCase):
    def test_public_anubis_cli_wrapper_delegates_to_stable_cli(self) -> None:
        completed = run_cli("anubis_cli.py", "status")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("model:", completed.stdout)
        self.assertIn("qdrant:", completed.stdout)

    def test_canonical_cli_module_delegates_to_stable_cli(self) -> None:
        completed = run_cli("cli/main.py", "status")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("model:", completed.stdout)
        self.assertIn("qdrant:", completed.stdout)

    def test_unified_router_exposes_phase1_command_surface(self) -> None:
        self.assertEqual(
            LEGACY_CLI_COMMANDS,
            {"console", "exec", "run", "repl", "sync", "orchestrate"},
        )

        result = UnifiedCommandRouter().route("/status")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("TASK:", result.text)
        self.assertIn("Status", result.text)
        self.assertTrue(result.should_continue)


if __name__ == "__main__":
    unittest.main()
