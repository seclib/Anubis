from __future__ import annotations

import unittest

from anubis.agents.session import AgentAction, ExecutorAgent, PlannerAgent
from anubis.cli.loop import is_agent_turn, run_commands
from anubis.core.session import AgentOrchestrator, SessionRuntime, SessionSettings
from anubis.memory.session import SessionMemory
from anubis.tools.engine import ToolExecutionEngine
from anubis.tools.registry import ToolRegistry
from anubis.tools.session_tools import ListFilesTool, RunShellTool


class BrokenExecutor(ExecutorAgent):
    def decide(self, task: str, memory: SessionMemory, tools: list[str]) -> AgentAction:
        raise RuntimeError("decision exploded")


class LongPlanner(PlannerAgent):
    def plan(self, task: str, memory: SessionMemory) -> list[str]:
        return [f"step {index}" for index in range(10)]


class ClaudeCodeRuntimeTest(unittest.TestCase):
    def test_session_streams_architecture_turn_without_ollama(self) -> None:
        runtime = SessionRuntime()

        events = list(runtime.run("décris architecture UX terminal et anti-patterns"))

        event_types = [event.type for event in events]
        self.assertIn("session.started", event_types)
        self.assertIn("model.routed", event_types)
        self.assertIn("agent.message", event_types)
        self.assertIn("memory.retrieved", event_types)
        self.assertIn("assistant.token", event_types)
        self.assertEqual(events[-1].type, "session.done")
        self.assertIn("Architecture cible", events[-1].payload["result"])

    def test_natural_cli_command_uses_agent_stream(self) -> None:
        output: list[str] = []

        status = run_commands(
            ["architecture UX terminal et anti-patterns"],
            output_fn=output.append,
            session=SessionRuntime(),
        )

        self.assertEqual(status, 0)
        rendered = "".join(output)
        self.assertIn("Task:", rendered)
        self.assertIn("Model:", rendered)
        self.assertIn("Plan:", rendered)
        self.assertIn("Done.", rendered)

    def test_slash_commands_remain_router_commands(self) -> None:
        self.assertFalse(is_agent_turn("/status"))
        self.assertFalse(is_agent_turn("status"))
        self.assertTrue(is_agent_turn("explain the repo"))

    def test_shell_tool_is_bounded_and_structured(self) -> None:
        engine = ToolExecutionEngine(registry=ToolRegistry([RunShellTool(), ListFilesTool()]))

        result = engine.execute("run_shell", {"cmd": "printf anubis", "timeout": 5})
        denied = engine.execute("run_shell", {"cmd": "rm -rf /tmp/anubis-nope"})

        self.assertTrue(result["success"])
        self.assertEqual(result["output"]["stdout"], "anubis")
        self.assertFalse(denied["success"])
        self.assertIn("destructive", denied["error"])

    def test_anubis_code_session_commands_are_runtime_backed(self) -> None:
        runtime = SessionRuntime()
        output: list[str] = []

        status = run_commands(
            ["/anubis", "/tools", "/model qwen2.5", "/auto on", "/memory"],
            output_fn=output.append,
            session=runtime,
        )

        rendered = "".join(output)
        self.assertEqual(status, 0)
        self.assertIn("ANUBIS CODE:", rendered)
        self.assertIn("read_file", rendered)
        self.assertIn("default: qwen2.5", rendered)
        self.assertIn("state: on", rendered)
        self.assertTrue(runtime.settings.autonomous)

    def test_session_started_event_exposes_autonomous_settings(self) -> None:
        runtime = SessionRuntime()
        runtime.settings.autonomous = True

        first_event = next(runtime.run("architecture UX terminal et anti-patterns"))

        self.assertEqual(first_event.type, "session.started")
        self.assertTrue(first_event.payload["autonomous"])

    def test_runtime_always_emits_final_fallback_on_executor_error(self) -> None:
        runtime = SessionRuntime(orchestrator=AgentOrchestrator(executor=BrokenExecutor()))

        events = list(runtime.run("fix the cli"))

        self.assertIn("error", [event.type for event in events])
        self.assertEqual(events[-1].type, "session.done")
        self.assertIn("I stopped this run", events[-1].payload["result"])

    def test_guardrail_blocks_tool_spam_before_execution(self) -> None:
        runtime = SessionRuntime(settings=SessionSettings(max_tool_calls=0))

        events = list(runtime.run("cat anubis/cli/prompt.py"))

        event_types = [event.type for event in events]
        self.assertIn("guardrail.triggered", event_types)
        self.assertNotIn("tool.request", event_types)
        self.assertEqual(events[-1].type, "session.done")
        self.assertIn("tool call limit reached", events[-1].payload["result"])

    def test_planning_is_truncated_by_guardrail(self) -> None:
        runtime = SessionRuntime(
            settings=SessionSettings(max_plan_steps=3),
            orchestrator=AgentOrchestrator(planner=LongPlanner()),
        )

        events = list(runtime.run("architecture UX terminal et anti-patterns"))
        plan_events = [event for event in events if event.type == "agent.message" and "plan" in event.payload]

        self.assertTrue(any(event.type == "guardrail.triggered" for event in events))
        self.assertEqual(len(plan_events[0].payload["plan"]), 3)

    def test_step_limit_produces_final_answer(self) -> None:
        runtime = SessionRuntime(settings=SessionSettings(max_steps=0))

        events = list(runtime.run("architecture UX terminal et anti-patterns"))

        self.assertEqual(events[-1].type, "session.done")
        self.assertIn("step limit reached", events[-1].payload["result"])


if __name__ == "__main__":
    unittest.main()
