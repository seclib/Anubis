import unittest

from backend.skills.dsl_runtime import (
    DslRuntime,
    DslRuntimeError,
    LlmHandler,
    MemoryConnector,
)


class DslRuntimeTest(unittest.TestCase):
    def test_executes_supported_operations_step_by_step(self) -> None:
        calls: list[str] = []
        runtime = DslRuntime(
            memory=MemoryConnector(
                search_memory=lambda query, limit=8: [{"source": "obsidian", "text": f"memory:{query}", "limit": limit}],
                query_qdrant=lambda query, limit=8: [{"source": "qdrant", "text": f"vector:{query}", "limit": limit}],
            ),
            llm=LlmHandler(lambda prompt, context: {"prompt": prompt, "context_count": len(context)}),
            tools={"format_report": lambda title, body: f"{title}: {body}"},
            allowed_tools={"format_report"},
        )
        skill = {
            "name": "grounded_report",
            "trigger": "build report",
            "steps": [
                {"id": 1, "action": "SEARCH_MEMORY", "input": {"query": "${query}", "limit": 2}, "save_as": "memory"},
                {"id": 2, "action": "QUERY_QDRANT", "input": {"query": "${query}", "limit": 3}, "save_as": "vectors"},
                {"id": 3, "action": "IF", "input": {"condition": "EXISTS(${memory})", "then": 4, "else": 6}},
                {"id": 4, "action": "CALL_LLM", "input": {"prompt": "summarize", "context": ["memory", "vectors"]}, "save_as": "draft"},
                {"id": 5, "action": "RUN_TOOL", "input": {"name": "format_report", "args": {"title": "Answer", "body": "${draft.prompt}"}}, "save_as": "report"},
                {"id": 6, "action": "RETURN", "input": {"value": "${report}"}},
            ],
        }

        result = runtime.execute(skill, {"query": "firewall hardening"})

        self.assertTrue(result.ok)
        self.assertEqual(result.value, "Answer: summarize")
        self.assertEqual([trace.action for trace in result.trace], ["SEARCH_MEMORY", "QUERY_QDRANT", "IF", "CALL_LLM", "RUN_TOOL", "RETURN"])
        self.assertEqual(calls, [])

    def test_then_operation_can_mark_branch_entry(self) -> None:
        runtime = DslRuntime()
        skill = {
            "name": "then_marker",
            "steps": [
                {"id": 1, "action": "IF", "input": {"condition": "EXISTS(${query})", "then_step": 2, "else_step": 3}},
                {"id": 2, "action": "THEN", "input": {"value": "branch entered"}, "save_as": "marker"},
                {"id": 3, "action": "RETURN", "input": {"value": "${marker}"}},
            ],
        }

        result = runtime.execute(skill, {"query": "x"})

        self.assertTrue(result.ok)
        self.assertEqual(result.value, "branch entered")

    def test_strict_tool_whitelist_blocks_unapproved_tool(self) -> None:
        runtime = DslRuntime(tools={"format_report": lambda: "ok"}, allowed_tools={"format_report"})
        skill = {
            "name": "blocked_tool",
            "steps": [
                {"id": 1, "action": "RUN_TOOL", "input": {"name": "not_allowed", "args": {}}},
                {"id": 2, "action": "RETURN", "input": {"value": "unreachable"}},
            ],
        }

        result = runtime.execute(skill, {"query": "x"})

        self.assertFalse(result.ok)
        self.assertIn("tool not whitelisted", result.variables["error"])

    def test_run_tool_rejects_raw_execution_surface(self) -> None:
        runtime = DslRuntime(tools={"format_report": lambda body: body}, allowed_tools={"format_report"})
        skill = {
            "name": "unsafe_args",
            "steps": [
                {
                    "id": 1,
                    "action": "RUN_TOOL",
                    "input": {"name": "format_report", "args": {"command": "python -c 'print(1)'"}},
                },
            ],
        }

        result = runtime.execute(skill, {"query": "x"})

        self.assertFalse(result.ok)
        self.assertIn("forbidden execution surface", result.variables["error"])

    def test_rejects_backward_if_jump_for_determinism(self) -> None:
        runtime = DslRuntime()
        skill = {
            "name": "loop",
            "steps": [
                {"id": 1, "action": "THEN", "input": {"value": True}},
                {"id": 2, "action": "IF", "input": {"condition": "EXISTS(${query})", "then_step": 1}},
            ],
        }

        with self.assertRaises(DslRuntimeError):
            runtime.execute(skill, {"query": "x"})

    def test_rejects_duplicate_step_ids(self) -> None:
        runtime = DslRuntime()
        skill = {
            "name": "duplicate",
            "steps": [
                {"id": 1, "action": "THEN", "input": {"value": True}},
                {"id": 1, "action": "RETURN", "input": {"value": True}},
            ],
        }

        with self.assertRaises(DslRuntimeError):
            runtime.execute(skill, {})


if __name__ == "__main__":
    unittest.main()
