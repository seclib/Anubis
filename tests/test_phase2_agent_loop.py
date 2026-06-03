import unittest

from backend.agent.agent_loop import AgentLoop
from backend.agent.executor import Executor
from backend.agent.task_manager import TaskManager


class FakeCompressedContext:
    text = "[1] implementation.md:0-20 score=1.0\nPHASE 1"
    chunks = [
        {
            "path": "implementation.md",
            "chunk_id": 0,
            "start": 0,
            "end": 20,
            "text": "PHASE 1",
            "score": 1.0,
            "metadata": {},
        }
    ]
    token_budget_chars = 7000


class FakeContextEngine:
    def context_for_task(self, task: str) -> FakeCompressedContext:
        return FakeCompressedContext()


class Phase2AgentLoopTest(unittest.TestCase):
    def test_loop_retrieves_plans_executes_and_verifies_with_phase1_tools(self) -> None:
        import tempfile
        from pathlib import Path

        calls: list[tuple[str, dict]] = []

        def fake_tool_invoker(tool: str, tool_input: dict | None = None) -> dict:
            payload = dict(tool_input or {})
            calls.append((tool, payload))
            output = {"path": payload.get("path", ""), "content": "PHASE 1"} if tool == "read_file" else {"ok": True}
            return {
                "tool": tool,
                "input": payload,
                "output": output,
                "success": True,
            }

        with tempfile.TemporaryDirectory(dir="state") as directory:
            loop = AgentLoop(
                executor=Executor(tool_invoker=fake_tool_invoker),
                context_engine=FakeContextEngine(),
                context_tool_invoker=fake_tool_invoker,
                task_manager=TaskManager(storage_dir=Path(directory)),
                max_iterations=2,
            )

            result = loop.run("Inspect implementation.md for PHASE 1")

        self.assertTrue(result.done)
        self.assertEqual(len(result.rounds), 1)
        self.assertIn(("git_diff", {}), calls)
        self.assertIn(("read_file", {"path": "implementation.md"}), calls)

        executed_tools = [
            step["step"]["tool"]
            for step in result.rounds[0].execution["steps"]
            if step["step"]["tool"] is not None
        ]
        self.assertEqual(executed_tools, ["read_file"])


if __name__ == "__main__":
    unittest.main()
