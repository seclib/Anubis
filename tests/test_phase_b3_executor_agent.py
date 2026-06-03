import unittest

from anubis.distributed import (
    ALLOWED_EXECUTOR_TOOLS,
    ExecutionStep,
    ExecutorAgent,
    InMemoryExecutionLogger,
    ToolIntegrationLayer,
)


class FakeToolRunner:
    def __init__(self, success: bool = True) -> None:
        self.success = success
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, tool: str, tool_input: dict | None = None) -> dict:
        input_data = dict(tool_input or {})
        self.calls.append((tool, input_data))
        return {
            "tool": tool,
            "input": input_data,
            "output": {"tool": tool, "input": input_data},
            "success": self.success,
            "logs": [f"fake {tool}"],
        }


class PhaseB3ExecutorAgentTest(unittest.TestCase):
    def test_executor_runs_exact_assigned_step_through_tool_layer(self) -> None:
        runner = FakeToolRunner()
        logger = InMemoryExecutionLogger()
        executor = ExecutorAgent(
            tools=ToolIntegrationLayer(runner=runner),
            logger=logger,
        )

        result = executor.execute_dict(
            {
                "step_id": "step_001",
                "tool": "read_file",
                "input": {"path": "README.md"},
            }
        )

        self.assertEqual(set(result), {"step_id", "success", "output", "logs"})
        self.assertEqual(result["step_id"], "step_001")
        self.assertTrue(result["success"])
        self.assertEqual(runner.calls, [("read_file", {"path": "README.md"})])
        self.assertIn('"tool": "read_file"', result["output"])
        self.assertEqual(len(logger.entries()), 1)

    def test_executor_reports_tool_failure_without_deciding_next_steps(self) -> None:
        runner = FakeToolRunner(success=False)
        executor = ExecutorAgent(tools=ToolIntegrationLayer(runner=runner))

        result = executor.execute(ExecutionStep("step_002", "run_command", {"cmd": "false"}))

        self.assertFalse(result.success)
        self.assertEqual(runner.calls, [("run_command", {"cmd": "false"})])
        self.assertTrue(any("success=False" in log for log in result.logs))
        self.assertNotIn("next", result.to_dict())

    def test_executor_blocks_non_allowlisted_tools(self) -> None:
        runner = FakeToolRunner()
        executor = ExecutorAgent(tools=ToolIntegrationLayer(runner=runner))

        result = executor.execute_dict(
            {
                "step_id": "step_003",
                "tool": "plan_task",
                "input": {"task": "do more"},
            }
        )

        self.assertFalse(result["success"])
        self.assertEqual(runner.calls, [])
        self.assertIn("not allowed", result["output"])

    def test_executor_validates_malformed_steps(self) -> None:
        executor = ExecutorAgent(tools=ToolIntegrationLayer(runner=FakeToolRunner()))

        result = executor.execute_dict({"id": "step_004", "input": {}})

        self.assertFalse(result["success"])
        self.assertIn("requires a non-empty tool", result["output"])

    def test_executor_tool_allowlist_matches_phase_b3_tools(self) -> None:
        self.assertEqual(
            ALLOWED_EXECUTOR_TOOLS,
            {
                "read_file",
                "write_file",
                "search_codebase",
                "run_command",
                "git_diff",
                "git_commit",
            },
        )


if __name__ == "__main__":
    unittest.main()
