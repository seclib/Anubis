from __future__ import annotations

import unittest
from unittest.mock import patch

from anubis.cli.command_router import CommandRouteResult, LEGACY_CLI_COMMANDS, UnifiedCommandRouter
from anubis.cli.main import build_parser


class CliPhase1UnificationTest(unittest.TestCase):
    def test_build_parser_exposes_legacy_command_surface(self) -> None:
        parser = build_parser()

        for command in (*sorted(LEGACY_CLI_COMMANDS), "status", "route"):
            with self.subTest(command=command):
                args = parser.parse_args([command, "task"] if command in {"run", "route", "orchestrate"} else [command])
                self.assertEqual(args.command, command)

    def test_unified_router_handles_package_status_without_legacy_loader(self) -> None:
        with patch("anubis_cli_loader.get_attr", side_effect=AssertionError("legacy loader should not be used")):
            result = UnifiedCommandRouter().route("/status")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("TASK:", result.text)
        self.assertIn("Status", result.text)
        self.assertTrue(result.should_continue)

    def test_unified_router_delegates_legacy_domain_commands_lazily(self) -> None:
        class LegacyRouter:
            def route(self, line: str) -> CommandRouteResult:
                return CommandRouteResult(f"legacy routed: {line}")

        with patch("anubis_cli_loader.get_attr", return_value=LegacyRouter):
            result = UnifiedCommandRouter().route("/rag qdrant")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.text, "legacy routed: /rag qdrant")


if __name__ == "__main__":
    unittest.main()
