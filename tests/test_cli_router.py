import unittest

from anubis.core.router import CommandRouter as CoreCommandRouter
from cli.router import CommandRouter
from modules.osint.schemas import AdapterExecution, IdentityReport, OsintReport


class CommandRouterTest(unittest.TestCase):
    def test_legacy_cli_router_exports_core_router(self) -> None:
        self.assertIs(CommandRouter, CoreCommandRouter)

    def test_routes_unknown_command_to_clean_error(self) -> None:
        result = CommandRouter().route("/missing value")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.task, "Parse command")
        self.assertEqual(result.result, "unknown command: /missing\nrun: /help")

    def test_help_is_grouped_and_minimal(self) -> None:
        result = CommandRouter().route("/help")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.task, "Help")
        self.assertIn("system:", result.result)
        self.assertIn("execution:", result.result)
        self.assertIn("agents:", result.result)

    def test_status_reports_runtime_summary(self) -> None:
        result = CommandRouter().route("/status")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.task, "Status")
        self.assertIn("runtime: ready", result.result)
        self.assertIn("agents: 4", result.result)

    def test_build_updates_builder_state(self) -> None:
        result = CommandRouter().route("/build command router")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status["builder"], "completed")
        self.assertIn("build task accepted", result.result)

    def test_agent_spawn_adds_agent_to_state(self) -> None:
        router = CommandRouter()

        result = router.route("/agent spawn reviewer")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.task, "AGENT SYSTEM")
        self.assertEqual(result.status["reviewer"], "idle")
        self.assertEqual(result.result, "reviewer spawned")

    def test_agent_list_returns_status_snapshot(self) -> None:
        result = CommandRouter().route("/agent list")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.task, "AGENT SYSTEM")
        self.assertEqual(result.result, "ok")
        self.assertEqual(result.status["builder"], "idle")

    def test_swarm_generates_aggregated_result(self) -> None:
        result = CommandRouter().route("/swarm build app")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("assignments:", result.result)
        self.assertIn("aggregate: combined swarm result prepared", result.result)
        self.assertEqual(result.status["orchestrator"], "active")

    def test_osint_routes_to_native_module(self) -> None:
        router = CommandRouter()
        router.osint = FakeOsintModule()

        result = router.route("/osint @username")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.task, "OSINT @username")
        self.assertEqual(result.status["osint"], "completed")
        self.assertIn('"usernames": [', result.result)
        self.assertIn('"username"', result.result)

    def test_exit_stops_loop(self) -> None:
        result = CommandRouter().route("/exit")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.should_continue)
        self.assertEqual(result.result, "session closed")


class FakeOsintModule:
    def run(self, target: str) -> AdapterExecution:
        return AdapterExecution(report=OsintReport(identity=IdentityReport(usernames=[target.lstrip("@")])))


if __name__ == "__main__":
    unittest.main()
