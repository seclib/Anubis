import unittest

from runtime.orchestration_engine import AnubisOrchestrationEngine
from retrieval.memory_router import MemoryRouter


class FakePluginManager:
    def __init__(self) -> None:
        self.queries = []

    def resolve(self, query: str) -> dict:
        self.queries.append(query)
        return {
            "query": query,
            "matches": ("cybersec",),
            "routes": [{"plugin": "cybersec", "trigger": "firewall", "score": 0.9}],
            "active_context": [{"plugin": "cybersec", "skills": ["# skill: firewall"]}],
        }


class FakeAgent:
    def __init__(self) -> None:
        self.context = None

    def run(self, task, context):
        self.context = context
        memory_context = context["memory"]["context"]
        return {
            "accepted": True,
            "answer": f"Grounded answer using {memory_context[0]['path']}",
        }


class FakeRetriever:
    def __init__(self, rows):
        self.rows = rows

    def search(self, query, limit=8):
        return self.rows[:limit]


class OrchestrationEngineTest(unittest.IsolatedAsyncioTestCase):
    async def test_runs_full_async_pipeline(self) -> None:
        plugins = FakePluginManager()
        agent = FakeAgent()
        memory = MemoryRouter(
            obsidian=FakeRetriever(
                [
                    {
                        "path": "skills/firewall.md",
                        "text": "Firewall procedure: deny inbound by default.",
                        "keywords": ["firewall", "procedure"],
                        "confidence": 0.95,
                    }
                ]
            ),
            qdrant=FakeRetriever(
                [
                    {
                        "text": "Similar firewall hardening memory.",
                        "score": 0.75,
                    }
                ]
            ),
        )
        events = []
        engine = AnubisOrchestrationEngine(
            plugin_manager=plugins,  # type: ignore[arg-type]
            memory_router=memory,
            agent_executor=agent,
        )

        result = await engine.run("firewall procedure", progress=events.append, stream=True)

        self.assertTrue(result.accepted)
        self.assertIn("skills/firewall.md", result.answer)
        self.assertEqual(plugins.queries, ["firewall procedure"])
        self.assertEqual(agent.context["plugins"]["matches"], ("cybersec",))
        self.assertIn("SECURITY RULES", agent.context["security"]["instruction_context"])
        self.assertEqual(
            [event.stage for event in result.events[:7]],
            ["input", "plugins", "memory", "security", "runtime", "agent", "output"],
        )
        self.assertTrue(any(event.kind == "token" for event in events))

    async def test_stream_yields_events_until_final_output(self) -> None:
        engine = AnubisOrchestrationEngine(
            plugin_manager=FakePluginManager(),  # type: ignore[arg-type]
            memory_router=MemoryRouter(
                obsidian=FakeRetriever(
                    [
                        {
                            "path": "truth.md",
                            "text": "Canonical truth: Obsidian is structured memory.",
                            "keywords": ["canonical", "truth", "obsidian"],
                            "confidence": 0.95,
                        }
                    ]
                ),
                qdrant=FakeRetriever([]),
            ),
            agent_executor=lambda _task, _context: {"accepted": True, "answer": "final answer"},
        )

        events = [event async for event in engine.stream("canonical truth")]

        self.assertEqual(events[-1].stage, "output")
        self.assertEqual(events[-1].kind, "final")
        self.assertTrue(any(event.kind == "token" and event.message == "final" for event in events))


if __name__ == "__main__":
    unittest.main()
