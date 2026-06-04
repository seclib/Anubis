from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from time import monotonic
from typing import Any
from uuid import uuid4

from anubis.agents.session import ExecutorAgent, PlannerAgent, ReviewerAgent
from anubis.core.session_events import SessionEvent
from anubis.llm import OllamaClient, OllamaRouter
from anubis.memory.session import SessionMemory
from anubis.tools.engine import ToolExecutionEngine
from anubis.tools.registry import ToolRegistry
from anubis.tools.session_tools import session_tools


@dataclass
class SessionSettings:
    autonomous: bool = False
    max_steps: int = 8
    max_plan_steps: int = 6
    max_llm_calls: int = 4
    max_tool_calls: int = 12
    max_same_tool_calls: int = 1
    logical_timeout_seconds: float = 300.0
    shell_timeout: int = 120


@dataclass
class RunGuard:
    settings: SessionSettings
    started_at: float
    steps: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    tool_call_counts: dict[tuple[str, str], int] | None = None

    def __post_init__(self) -> None:
        if self.tool_call_counts is None:
            self.tool_call_counts = {}

    def tick(self, stage: str) -> str | None:
        self.steps += 1
        if self.steps > self.settings.max_steps:
            return f"step limit reached during {stage}"
        return self.check_timeout(stage)

    def check_timeout(self, stage: str) -> str | None:
        elapsed = monotonic() - self.started_at
        if elapsed > self.settings.logical_timeout_seconds:
            return f"logical timeout reached during {stage}"
        return None

    def record_llm_call(self) -> str | None:
        self.llm_calls += 1
        if self.llm_calls > self.settings.max_llm_calls:
            return "LLM call limit reached"
        return self.check_timeout("llm")

    def allow_tool(self, tool: str, args: dict[str, Any]) -> str | None:
        self.tool_calls += 1
        if self.tool_calls > self.settings.max_tool_calls:
            return "tool call limit reached"
        key = (tool, _stable_args(args))
        assert self.tool_call_counts is not None
        self.tool_call_counts[key] = self.tool_call_counts.get(key, 0) + 1
        if self.tool_call_counts[key] > self.settings.max_same_tool_calls:
            return f"repeated tool call blocked: {tool}"
        return self.check_timeout(f"tool {tool}")


class AgentOrchestrator:
    def __init__(
        self,
        *,
        planner: PlannerAgent | None = None,
        executor: ExecutorAgent | None = None,
        reviewer: ReviewerAgent | None = None,
        tools: ToolExecutionEngine | None = None,
        memory: SessionMemory | None = None,
    ) -> None:
        self.planner = planner or PlannerAgent()
        self.executor = executor or ExecutorAgent()
        self.reviewer = reviewer or ReviewerAgent()
        self.tools = tools or ToolExecutionEngine(registry=ToolRegistry(session_tools()))
        self.memory = memory or SessionMemory()

    def run(self, task: str, settings: SessionSettings | None = None) -> Iterator[SessionEvent]:
        active_settings = settings or SessionSettings()
        guard = RunGuard(active_settings, monotonic())
        self.memory.add_message("user", task)
        blocked = guard.tick("planning")
        if blocked:
            yield from _blocked_events(task, blocked, self.memory)
            return

        yield SessionEvent("agent.state", "planner running", {"agent": "planner", "state": "running"})
        plan = self.planner.plan(task, self.memory)
        if len(plan) > active_settings.max_plan_steps:
            plan = plan[: active_settings.max_plan_steps]
            yield SessionEvent(
                "guardrail.triggered",
                "plan truncated",
                {"reason": "plan step limit reached", "max_plan_steps": active_settings.max_plan_steps},
            )
        yield SessionEvent("agent.message", "plan ready", {"agent": "planner", "plan": plan})

        blocked = guard.tick("memory retrieval")
        if blocked:
            yield from _blocked_events(task, blocked, self.memory)
            return
        recalled = self.memory.retrieve(task)
        yield SessionEvent("memory.retrieved", "session memory searched", {"items": recalled})

        blocked = guard.tick("decision")
        if blocked:
            yield from _blocked_events(task, blocked, self.memory)
            return
        tool_names = [tool.name for tool in self.tools.discover()]
        yield SessionEvent("agent.state", "executor running", {"agent": "executor", "state": "running"})
        blocked = guard.record_llm_call()
        if blocked:
            yield from _blocked_events(task, blocked, self.memory)
            return
        action = self.executor.decide(task, self.memory, tool_names)
        yield SessionEvent(
            "routing.decision",
            action.reason or "action selected",
            {"intent": action.intent, "tool": action.tool, "args": action.args or {}},
        )

        result = None
        final_text = ""
        if action.intent == "tool" and action.tool not in {"", "none"}:
            args = action.args or {}
            blocked = guard.allow_tool(action.tool, args)
            if blocked:
                yield SessionEvent(
                    "guardrail.triggered",
                    blocked,
                    {"tool": action.tool, "args": args, "tool_calls": guard.tool_calls},
                )
                final_text = _fallback_response(task, blocked)
                self.memory.add_message("assistant", final_text)
                self.memory.remember(f"Task blocked: {blocked}")
                yield from _final_events(final_text, "blocked by guardrail")
                return
            yield SessionEvent("tool.request", f"{action.tool} requested", {"tool": action.tool, "args": args})
            result = self.tools.execute(action.tool, args)
            self.memory.add_tool_result(dict(result))
            event_type = "tool.result" if result["success"] else "tool.error"
            yield SessionEvent(event_type, f"{action.tool} completed", {"result": result})
            final_text = _summarize_tool_result(result)
        else:
            args = action.args or {}
            final_text = str(args.get("result") or "Done.")

        blocked = guard.tick("review")
        if blocked:
            yield from _blocked_events(task, blocked, self.memory)
            return
        yield SessionEvent("agent.state", "reviewer running", {"agent": "reviewer", "state": "running"})
        review = self.reviewer.review(task, result, self.memory)
        yield SessionEvent("agent.message", review, {"agent": "reviewer"})

        self.memory.add_message("assistant", final_text)
        self.memory.remember(f"Task result: {final_text[:500]}")
        yield from _final_events(final_text, review)


class SessionRuntime:
    def __init__(
        self,
        *,
        session_id: str | None = None,
        orchestrator: AgentOrchestrator | None = None,
        llm_router: OllamaRouter | None = None,
        llm_client: OllamaClient | None = None,
        settings: SessionSettings | None = None,
    ) -> None:
        self.session_id = session_id or uuid4().hex
        self.llm_router = llm_router or OllamaRouter()
        self.llm_client = llm_client or OllamaClient()
        self.settings = settings or SessionSettings()
        self.orchestrator = orchestrator or AgentOrchestrator(
            executor=ExecutorAgent(client=self.llm_client, router=self.llm_router)
        )

    @property
    def memory(self) -> SessionMemory:
        return self.orchestrator.memory

    def run(self, task: str) -> Iterator[SessionEvent]:
        yield SessionEvent(
            "session.started",
            "session turn started",
            {
                "session_id": self.session_id,
                "task": task,
                "autonomous": self.settings.autonomous,
                "max_tool_calls": self.settings.max_tool_calls,
            },
        )
        routed = self.llm_router.route(task)
        yield SessionEvent("model.routed", routed.reason, {"model": routed.model})
        try:
            yield from self.orchestrator.run(task, self.settings)
        except Exception as exc:
            final_text = _fallback_response(task, f"{exc.__class__.__name__}: {exc}")
            self.memory.add_message("assistant", final_text)
            self.memory.remember(f"Task failed with fallback: {exc.__class__.__name__}")
            yield SessionEvent(
                "error",
                "agent runtime failed",
                {"error": str(exc), "type": exc.__class__.__name__, "recoverable": True},
            )
            yield from _final_events(final_text, "fallback after runtime error")


def _summarize_tool_result(result: dict) -> str:
    if not result.get("success"):
        return f"Tool `{result.get('tool')}` failed: {result.get('error') or result.get('output')}"
    output = result.get("output")
    if isinstance(output, dict) and "content" in output:
        content = str(output["content"])
        return content if len(content) < 4000 else content[:4000] + "\n...[truncated]"
    return f"Tool `{result.get('tool')}` completed: {output}"


def _tokens(text: str) -> list[str]:
    parts = text.split(" ")
    return [(part + " ") for part in parts[:-1]] + ([parts[-1]] if parts else [])


def _stable_args(args: dict[str, Any]) -> str:
    items = sorted((str(key), repr(value)) for key, value in args.items())
    return "|".join(f"{key}={value}" for key, value in items)


def _fallback_response(task: str, reason: str) -> str:
    clean_task = " ".join(task.split()) or "the requested task"
    return (
        "I stopped this run before it became unstable. "
        f"Reason: {reason}. "
        f"Task: {clean_task}. "
        "You can retry with a narrower request or inspect the last visible tool event."
    )


def _final_events(final_text: str, review: str) -> Iterator[SessionEvent]:
    safe_text = final_text.strip() or "I stopped without producing a model answer, but the runtime returned a safe fallback."
    for token in _tokens(safe_text):
        yield SessionEvent("assistant.token", token, {"text": token})
    yield SessionEvent("memory.stored", "turn stored in session memory", {})
    yield SessionEvent("session.done", "turn complete", {"result": safe_text, "review": review})


def _blocked_events(task: str, reason: str, memory: SessionMemory) -> Iterator[SessionEvent]:
    final_text = _fallback_response(task, reason)
    memory.add_message("assistant", final_text)
    memory.remember(f"Task blocked: {reason}")
    yield SessionEvent("guardrail.triggered", reason, {"reason": reason})
    yield from _final_events(final_text, "blocked by guardrail")


__all__ = ["AgentOrchestrator", "RunGuard", "SessionRuntime", "SessionSettings"]
