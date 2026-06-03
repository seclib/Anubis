import tempfile
import unittest
from pathlib import Path

from backend.agent.agent_loop import AgentLoop
from backend.agent.executor import Executor
from backend.agent.task_manager import TaskManager, TaskStatus


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


class Phase6TaskManagerTest(unittest.TestCase):
    def test_task_lifecycle_and_replay_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            manager = TaskManager(storage_dir=Path(directory))
            task = manager.create_task("Build task manager", {"source": "test"})

            self.assertEqual(task.status, TaskStatus.PENDING)
            manager.start_task(task.id)
            manager.update_context(task.id, {"compressed": "context"})
            manager.update_plan(task.id, {"steps": [{"id": 1, "tool": "read_file"}]})
            manager.log_action(task.id, "tool_invoked", {"tool": "read_file", "success": True})
            manager.complete_task(task.id, "verified")

            snapshot = manager.snapshot(task.id)
            replay = manager.replay(task.id)

            self.assertEqual(snapshot["status"], "done")
            self.assertEqual(snapshot["goal"], "Build task manager")
            self.assertEqual(snapshot["context"], {"compressed": "context"})
            self.assertEqual(snapshot["plan"]["steps"][0]["tool"], "read_file")
            self.assertEqual(replay[0]["event"], "created")
            self.assertEqual(replay[-1]["event"], "status_changed")

            reloaded = TaskManager(storage_dir=Path(directory))
            self.assertEqual(reloaded.snapshot(task.id)["status"], "done")

    def test_invalid_status_transition_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            manager = TaskManager(storage_dir=Path(directory))
            task = manager.create_task("Invalid transition")

            with self.assertRaises(ValueError):
                manager.complete_task(task.id)

    def test_agent_loop_records_task_debug_history(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            manager = TaskManager(storage_dir=Path(directory))
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

            loop = AgentLoop(
                executor=Executor(tool_invoker=fake_tool_invoker),
                context_engine=FakeContextEngine(),
                context_tool_invoker=fake_tool_invoker,
                task_manager=manager,
                max_iterations=1,
            )

            result = loop.run("Inspect implementation.md for PHASE 1")
            snapshot = manager.snapshot(result.task_id)
            events = [event["event"] for event in manager.replay(result.task_id)]

            self.assertTrue(result.done)
            self.assertEqual(snapshot["status"], "done")
            self.assertIn("created", events)
            self.assertIn("context_updated", events)
            self.assertIn("plan_updated", events)
            self.assertIn("agent_round", events)
            self.assertIn(("read_file", {"path": "implementation.md"}), calls)


if __name__ == "__main__":
    unittest.main()
