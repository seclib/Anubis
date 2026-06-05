import tempfile
import unittest
from pathlib import Path

from anubis.core.agent_loop.context import TaskContextProvider
from anubis.core.agent_loop.loop import ProductionAgentLoop
from anubis.core.executor.executor import ToolDrivenExecutor
from anubis.core.planner.planner import DefaultPlanner
from anubis.tools import ToolExecutionEngine
from anubis.tools.filesystem import ReadFileTool, WriteFileTool
from anubis.tools.logging import ToolCallLogger
from anubis.tools.registry import ToolRegistry
from anubis.types import AgentContext, TaskSnapshot


def task(goal: str, context: dict | None = None) -> TaskSnapshot:
    return {
        "id": "task-1",
        "goal": goal,
        "status": "pending",
        "context": context or {},
        "plan": {},
        "history": [],
    }


class RecordingContextProvider(TaskContextProvider):
    def __init__(self) -> None:
        self.calls = 0

    def get_context(self, task: TaskSnapshot) -> AgentContext:
        self.calls += 1
        return super().get_context(task)


class FlakyToolEngine:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, name: str, input: dict) -> dict:
        self.calls += 1
        success = self.calls > 1
        return {
            "tool": name,
            "input": input,
            "output": {"path": input.get("path", ""), "content": "ok"} if success else {"type": "failed"},
            "success": success,
            "error": None if success else "first attempt failed",
            "logs": ["called"],
            "duration_ms": 1,
        }


class AgentLoopEngineTest(unittest.TestCase):
    def test_task_plan_execute_verify_completes_with_tool_only_file_steps(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            target = Path(directory) / "agent-loop.txt"
            engine = ToolExecutionEngine(
                registry=ToolRegistry([ReadFileTool(), WriteFileTool()]),
                logger=ToolCallLogger(Path(directory) / "tool_calls.jsonl"),
            )
            loop = ProductionAgentLoop(executor=ToolDrivenExecutor(engine), max_retries=0)

            result = loop.run(task("write file", {"path": str(target), "content": "hello"}))

            self.assertEqual(result["status"], "done")
            self.assertEqual(target.read_text(encoding="utf-8"), "hello")
            self.assertEqual([step["tool"] for step in result["plan"]["steps"]], ["write_file", "read_file"])
            states = [event["payload"].get("state") for event in result["history"] if event["event"] == "state_changed"]
            self.assertEqual(states, ["planning", "executing", "verifying"])

    def test_context_is_injected_before_planning(self) -> None:
        provider = RecordingContextProvider()
        loop = ProductionAgentLoop(context_provider=provider, max_retries=0)

        result = loop.run(task("inspect missing.txt", {"compressed": "relevant context"}))

        self.assertEqual(provider.calls, 1)
        self.assertEqual(result["plan"]["metadata"]["context_chars"], len("relevant context"))

    def test_step_failure_triggers_retry_and_replan(self) -> None:
        tool_engine = FlakyToolEngine()
        loop = ProductionAgentLoop(
            executor=ToolDrivenExecutor(tool_engine),  # type: ignore[arg-type]
            planner=DefaultPlanner(),
            max_retries=1,
        )

        result = loop.run(task("inspect README.md"))

        self.assertEqual(result["status"], "done")
        self.assertEqual(tool_engine.calls, 2)
        states = [event["payload"].get("state") for event in result["history"] if event["event"] == "state_changed"]
        self.assertIn("retrying", states)
        iterations = [event for event in result["history"] if event["event"] == "agent_iteration"]
        self.assertEqual(len(iterations), 2)

    def test_unsupported_task_fails_without_direct_action(self) -> None:
        loop = ProductionAgentLoop(max_retries=0)

        result = loop.run(task("explain architecture"))

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["plan"]["steps"], [])


if __name__ == "__main__":
    unittest.main()
