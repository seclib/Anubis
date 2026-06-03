import tempfile
import unittest
from pathlib import Path

from backend.agent.agent_loop import AgentLoop
from backend.agent.executor import Executor
from backend.agent.planner import AgentContext, Plan, PlanStep
from backend.agent.task_manager import TaskManager
from backend.agent.verifier import (
    Verifier,
    validate_command_output,
    validate_file_state,
)


class FakeCompressedContext:
    text = ""
    chunks: list[dict] = []
    token_budget_chars = 7000


class FakeContextEngine:
    def context_for_task(self, task: str) -> FakeCompressedContext:
        return FakeCompressedContext()


class FailingThenPassingPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def plan(self, task: str, context: AgentContext) -> Plan:
        self.calls += 1
        return Plan(
            task=task,
            context=context,
            steps=[
                PlanStep(
                    id=1,
                    goal="Run validation command",
                    tool="run_command",
                    input={"cmd": "pytest"},
                )
            ],
        )


class Phase7VerificationLoopTest(unittest.TestCase):
    def test_validate_file_state_detects_write_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            path = Path(directory) / "phase7.txt"
            path.write_text("actual", encoding="utf-8")
            result = {
                "tool": "write_file",
                "input": {"path": str(path), "content": "expected"},
                "output": {"path": str(path), "bytes": len("expected")},
                "success": True,
            }

            validation = validate_file_state(result)

            self.assertFalse(validation["success"])
            self.assertIn("mismatch", validation["reason"])

    def test_validate_command_output_detects_nonzero_exit(self) -> None:
        validation = validate_command_output(
            {
                "tool": "run_command",
                "input": {"cmd": "pytest"},
                "output": {"code": 1, "stdout": "", "stderr": "failed", "timed_out": False},
                "success": True,
            }
        )

        self.assertFalse(validation["success"])
        self.assertIn("code 1", validation["reason"])

    def test_executor_marks_step_failed_when_validation_fails(self) -> None:
        def fake_tool_invoker(tool: str, tool_input: dict | None = None) -> dict:
            return {
                "tool": tool,
                "input": dict(tool_input or {}),
                "output": {"code": 1, "stdout": "", "stderr": "boom", "timed_out": False},
                "success": True,
            }

        context = AgentContext(task="run tests")
        plan = Plan(
            task="run tests",
            context=context,
            steps=[PlanStep(id=1, goal="Run tests", tool="run_command", input={"cmd": "pytest"})],
        )

        execution = Executor(tool_invoker=fake_tool_invoker).execute(plan)
        verification = Verifier().verify(execution)

        self.assertFalse(execution.steps[0].success)
        self.assertFalse(execution.steps[0].validation["success"])
        self.assertTrue(verification.retry)

    def test_agent_loop_retries_after_step_validation_failure(self) -> None:
        calls = 0

        def fake_tool_invoker(tool: str, tool_input: dict | None = None) -> dict:
            nonlocal calls
            calls += 1
            code = 1 if calls == 1 else 0
            return {
                "tool": tool,
                "input": dict(tool_input or {}),
                "output": {"code": code, "stdout": "", "stderr": "", "timed_out": False},
                "success": True,
            }

        with tempfile.TemporaryDirectory(dir="state") as directory:
            manager = TaskManager(storage_dir=Path(directory))
            loop = AgentLoop(
                planner=FailingThenPassingPlanner(),
                executor=Executor(tool_invoker=fake_tool_invoker),
                context_engine=FakeContextEngine(),
                context_tool_invoker=lambda tool, tool_input=None: {
                    "tool": tool,
                    "input": dict(tool_input or {}),
                    "output": {"code": 0, "stdout": "", "stderr": "", "timed_out": False},
                    "success": True,
                },
                task_manager=manager,
                max_iterations=2,
            )

            result = loop.run("run tests")
            events = [event["event"] for event in manager.replay(result.task_id)]

        self.assertTrue(result.done)
        self.assertEqual(len(result.rounds), 2)
        self.assertIn("agent_round", events)
        self.assertIn("validation failed", result.rounds[0].verification.reason)


if __name__ == "__main__":
    unittest.main()
