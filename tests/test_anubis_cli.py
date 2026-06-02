import unittest

from cli.anubis import AnubisAgent, Terminal


class FakeLLM:
    def generate(self, prompt: str) -> str:
        return '{"steps":[{"id":1,"goal":"answer from memory","tool":null,"args":{}}]}'

    def stream(self, prompt: str):
        yield "final answer"


class AnubisCliTest(unittest.TestCase):
    def test_planner_parses_json_steps_without_tools(self) -> None:
        agent = AnubisAgent(llm=FakeLLM(), terminal=Terminal(quiet=True))
        plan = agent.plan(
            "explain docker error",
            memory=[{"path": "notes/docker.md", "heading": "Docker", "text": "Known error", "score": 0.9}],
            skills=[],
        )

        self.assertEqual(plan.steps[0].goal, "answer from memory")
        self.assertIsNone(plan.steps[0].tool)

    def test_non_shell_tools_are_not_accepted_from_plan(self) -> None:
        agent = AnubisAgent(llm=FakeLLM(), terminal=Terminal(quiet=True))
        steps = agent._parse_steps('{"steps":[{"id":1,"goal":"bad","tool":"write_file","args":{}}]}')

        self.assertEqual(steps[0].goal, "bad")
        self.assertIsNone(steps[0].tool)

    def test_context_retrieval_uses_qdrant_then_obsidian_fallback(self) -> None:
        agent = AnubisAgent(llm=FakeLLM(), terminal=Terminal(quiet=True))
        calls = []

        def retrieve_qdrant(query: str):
            calls.append(("qdrant", query))
            return []

        def search_obsidian(query: str):
            calls.append(("obsidian", query))
            return [{"source": "obsidian", "path": "notes/docker.md", "heading": "Docker", "text": "error", "score": 1.0}]

        agent.retrieve_qdrant = retrieve_qdrant
        agent.search_obsidian = search_obsidian

        context = agent.retrieve_context("docker error")

        self.assertEqual([name for name, _ in calls], ["qdrant", "obsidian"])
        self.assertEqual(context[0]["source"], "obsidian")


if __name__ == "__main__":
    unittest.main()
