import unittest
from unittest.mock import patch

from anubis.core.session_events import SessionEvent
from backend.agent.loop import AgentLoop
from backend.agent.shadow import ShadowAgentRunner


class FakeRuntime:
    def __init__(self) -> None:
        self.tasks: list[str] = []

    def run(self, task: str):
        self.tasks.append(task)
        yield SessionEvent("tool.result", "tool completed", {"result": {"tool": "read_file", "input": {"path": "note.md"}, "output": "ok", "success": True}})
        yield SessionEvent("session.done", "done", {"result": "core answer"})


class FakeTools:
    def rag_query(self, query: str):
        return [{"path": "note.md", "heading": "Note", "text": "retrieved context", "score": 0.9}]

    def reindex_memory(self) -> int:
        return 1


class FakeVault:
    def __init__(self) -> None:
        self.writes: list[tuple[str, str]] = []

    def write_note(self, path: str, content: str) -> None:
        self.writes.append((path, content))


class FakeMemory:
    def __init__(self) -> None:
        self.vault = FakeVault()

    def inject(self, text: str, target: str = "notes/inbox.md") -> str:
        return target


class FakeSkills:
    def search(self, query: str):
        return []


class AgentCoreBridgeTest(unittest.TestCase):
    def test_http_agent_facade_delegates_decisions_to_session_runtime(self) -> None:
        runtime = FakeRuntime()
        with (
            patch("backend.agent.loop.AgentTools", FakeTools),
            patch("backend.agent.loop.MarkdownMemory", FakeMemory),
            patch("backend.agent.loop.SkillRepository", FakeSkills),
        ):
            result = AgentLoop(runtime=runtime, shadow_runner=ShadowAgentRunner(enabled=False)).chat("summarize note")

        self.assertEqual(result["answer"], "core answer")
        self.assertEqual(result["chunks_used"][0]["path"], "note.md")
        self.assertEqual(result["actions"][0]["tool"], "read_file")
        self.assertIn("User request:\nsummarize note", runtime.tasks[0])
        self.assertIn("retrieved context", runtime.tasks[0])


if __name__ == "__main__":
    unittest.main()
