import json
import unittest

from backend.agent.multi_agent import MultiAgentLoop


class ScriptedLLM:
    def __init__(self, critic_acceptance: list[bool] | None = None, executor_plain_text: bool = False) -> None:
        self.critic_acceptance = critic_acceptance or [True]
        self.executor_plain_text = executor_plain_text
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        payload = json.loads(prompt)
        role = payload.get("role")
        self.calls.append(str(role))
        if role == "planner":
            return json.dumps(
                {
                    "steps": [
                        {"id": 1, "goal": "collect grounded evidence", "tool": None, "args": {}},
                        {"id": 2, "goal": "draft from evidence", "tool": None, "args": {}},
                    ]
                }
            )
        if role == "executor":
            if self.executor_plain_text:
                return "This raw prose must not become the final answer."
            return json.dumps(
                {
                    "answer": "Anubis uses a Planner Executor Critic loop grounded in retrieved memory.",
                    "citations": ["docs/anubis.md"],
                }
            )
        if role == "critic":
            accepted = self.critic_acceptance.pop(0) if self.critic_acceptance else True
            return json.dumps(
                {
                    "accepted": accepted,
                    "retry": not accepted,
                    "reason": "approved" if accepted else "revise with tighter grounding",
                }
            )
        return "{}"


class FakeTools:
    def __init__(self, context: list[dict] | None = None) -> None:
        self.context = context or []
        self.queries: list[str] = []

    def search_rag(self, query: str) -> list[dict]:
        self.queries.append(query)
        return self.context

    def execute(self, tool: str, args: dict) -> dict:
        return {"tool": tool, "args": args}


class MultiAgentLoopTest(unittest.TestCase):
    def test_no_direct_answer_without_retrieved_context(self) -> None:
        llm = ScriptedLLM()
        result = MultiAgentLoop(llm=llm, tools=FakeTools(), max_rounds=2).run("explain Anubis")

        self.assertFalse(result["accepted"])
        self.assertEqual(result["answer"], "")
        self.assertEqual(result["history"][0]["critique"]["reason"], "no relevant memory was retrieved before execution")
        self.assertIn("plan", result["history"][0])

    def test_critic_can_force_retry(self) -> None:
        context = [
            {
                "path": "docs/anubis.md",
                "text": "Anubis uses a Planner Executor Critic loop grounded in retrieved memory.",
                "score": 0.9,
            }
        ]
        llm = ScriptedLLM(critic_acceptance=[False, True])
        tools = FakeTools(context)

        result = MultiAgentLoop(llm=llm, tools=tools, max_rounds=3).run("describe the Anubis agent loop")

        self.assertTrue(result["accepted"])
        self.assertEqual(len(result["history"]), 2)
        self.assertIn("revise with tighter grounding", tools.queries[1])
        self.assertIn("Planner Executor Critic", result["answer"])

    def test_executor_requires_structured_output(self) -> None:
        context = [
            {
                "path": "docs/anubis.md",
                "text": "Anubis uses retrieved memory as evidence before producing an answer.",
                "score": 0.9,
            }
        ]
        llm = ScriptedLLM(executor_plain_text=True)

        result = MultiAgentLoop(llm=llm, tools=FakeTools(context), max_rounds=1).run("what grounds Anubis answers")

        self.assertNotIn("raw prose", result["answer"])
        self.assertIn("retrieved memory", result["answer"])
        self.assertTrue(result["history"][0]["executor_output"]["structured"])


if __name__ == "__main__":
    unittest.main()
