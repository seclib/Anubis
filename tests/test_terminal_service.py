import tempfile
import unittest

from anubis.distributed import (
    AgentType,
    ResourceLimits,
    SandboxRuntime,
    SandboxRuntimeConfig,
    TerminalEventType,
    TerminalService,
)


class TerminalServiceTest(unittest.TestCase):
    def service(self, root: str) -> TerminalService:
        runtime = SandboxRuntime(
            SandboxRuntimeConfig(
                root_dir=root,
                default_limits=ResourceLimits(timeout_seconds=2.0, cpu_seconds=2, memory_mb=256),
            )
        )
        return TerminalService(runtime=runtime)

    def test_terminal_runs_command_inside_sandbox_and_records_events(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            session = service.create_session("task-terminal")

            result = service.run_command(session.session_id, "pwd")

            self.assertTrue(result.command.success)
            self.assertIn(session.workspace, result.command.output)
            self.assertEqual(tuple(event.event_type for event in result.events), (
                TerminalEventType.COMMAND_STARTED,
                TerminalEventType.OUTPUT,
                TerminalEventType.COMMAND_COMPLETED,
            ))
            self.assertEqual(service.history(session.session_id)[0].command, "pwd")

    def test_terminal_exposes_task_execution_logs(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            session = service.create_session("task-logs")

            service.run_command(session.session_id, "echo hello")
            logs = service.task_logs("task-logs")

            self.assertTrue(any(event.event_type == TerminalEventType.OUTPUT for event in logs))
            self.assertTrue(any("hello" in str(event.payload.get("text", "")) for event in logs))

    def test_terminal_history_is_capped(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            service = TerminalService(
                runtime=SandboxRuntime(SandboxRuntimeConfig(root_dir=root)),
                history_limit=2,
            )
            session = service.create_session("task-history")

            service.run_command(session.session_id, "echo one")
            service.run_command(session.session_id, "echo two")
            service.run_command(session.session_id, "echo three")

            self.assertEqual([entry.command for entry in service.history(session.session_id)], ["echo two", "echo three"])

    def test_terminal_denies_shell_for_non_executor_role(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            session = service.create_session("task-denied", agent_type=AgentType.PLANNER)

            result = service.run_command(session.session_id, "pwd")

            self.assertFalse(result.command.success)
            self.assertEqual(result.events[-1].event_type, TerminalEventType.COMMAND_DENIED)
            self.assertIn("not explicitly allowed", result.command.output)

    def test_terminal_rejects_shell_control_surface_through_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            session = service.create_session("task-shell")

            result = service.run_command(session.session_id, "echo safe && echo unsafe")

            self.assertFalse(result.command.success)
            self.assertIn("shell control", result.command.output)

    def test_terminal_rejects_destructive_commands(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            session = service.create_session("task-destructive")

            result = service.run_command(session.session_id, "rm -rf /tmp/anubis-nope")

            self.assertFalse(result.command.success)
            self.assertIn("forbidden command", result.command.output)

    def test_terminal_rejects_absolute_host_paths(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            session = service.create_session("task-host-path")

            result = service.run_command(session.session_id, "cat /etc/passwd")

            self.assertFalse(result.command.success)
            self.assertIn("absolute host paths", result.command.output)

    def test_terminal_rejects_inline_execution_flags(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            service = self.service(root)
            session = service.create_session("task-inline")

            result = service.run_command(session.session_id, "python3 -c 'print(123)'")

            self.assertFalse(result.command.success)
            self.assertIn("inline execution", result.command.output)


if __name__ == "__main__":
    unittest.main()
