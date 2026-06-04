import json
import tempfile
import unittest
from pathlib import Path

from anubis.core.agent_core import AgentCoreResult
from backend.agent.shadow import ShadowAgentRunner, ShadowRequest


class FakeCore:
    def run(self, request):
        return AgentCoreResult(
            request_id=request.request_id,
            answer="shadow answer",
            confidence=0.95,
            ok=True,
            duration_ms=1,
            events=[{"type": "session.done", "message": "done", "payload": {"result": "shadow answer"}}],
        )


class ShadowModeTest(unittest.TestCase):
    def test_shadow_runner_logs_active_and_shadow_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "shadow.jsonl"
            runner = ShadowAgentRunner(core=FakeCore(), log_path=log_path)

            runner.run_inline(
                ShadowRequest(
                    request_id="request-1",
                    prompt="hello",
                    context="retrieved context",
                    active_response={
                        "answer": "active answer",
                        "chunks_used": [{"path": "note.md"}],
                        "skills_used": [],
                        "actions": [],
                        "memory_path": "agent-runs/test.md",
                    },
                )
            )

            rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["mode"], "shadow")
        self.assertEqual(rows[0]["request_id"], "request-1")
        self.assertEqual(rows[0]["active"]["answer"], "active answer")
        self.assertEqual(rows[0]["shadow"]["answer"], "shadow answer")
        self.assertEqual(rows[0]["summary"]["shadow_confidence"], 0.95)
        self.assertFalse(rows[0]["summary"]["answers_exact_match"])


if __name__ == "__main__":
    unittest.main()
