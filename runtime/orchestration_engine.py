"""Final async orchestration engine for Anubis OS."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from inspect import isawaitable
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Mapping, Protocol

from backend.security import SecurityPipeline
from backend.skills import PluginManager, SkillExecutionEngine
from retrieval import MemoryRouter


@dataclass(frozen=True)
class OrchestrationEvent:
    stage: str
    kind: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrchestrationResult:
    task: str
    answer: str
    accepted: bool
    events: tuple[OrchestrationEvent, ...]
    plugins: dict[str, Any]
    memory: dict[str, Any]
    security: dict[str, Any]
    agent: dict[str, Any]


class AgentExecutor(Protocol):
    def run(self, task: str, context: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


ProgressCallback = Callable[[OrchestrationEvent], Any]


class DefaultAgentExecutor:
    """Adapter around the Planner -> Executor -> Critic loop."""

    def run(self, task: str, context: Mapping[str, Any]) -> Mapping[str, Any]:
        from backend.agent.multi_agent import MultiAgentLoop

        tools = ContextToolAdapter(context)
        result = MultiAgentLoop(tools=tools, max_rounds=2).run(task)
        return dict(result)


class ContextToolAdapter:
    """Small tool adapter exposing routed memory to the multi-agent loop."""

    def __init__(self, context: Mapping[str, Any]) -> None:
        self.context = context

    def search_rag(self, query: str) -> list[dict[str, Any]]:
        memory = self.context.get("memory")
        if isinstance(memory, Mapping):
            context = memory.get("context")
            if isinstance(context, list):
                return [dict(item) for item in context if isinstance(item, Mapping)]
        return []

    def execute(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"tool": tool, "args": args, "status": "not_executed_by_orchestrator"}


class AnubisOrchestrationEngine:
    def __init__(
        self,
        *,
        plugin_manager: PluginManager | None = None,
        memory_router: MemoryRouter | None = None,
        security: SecurityPipeline | None = None,
        skill_runtime: SkillExecutionEngine | None = None,
        agent_executor: AgentExecutor | Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self.plugin_manager = plugin_manager or PluginManager(root=Path("skills"))
        self.memory_router = memory_router or MemoryRouter()
        self.security = security or SecurityPipeline()
        self.skill_runtime = skill_runtime or SkillExecutionEngine()
        self.agent_executor = agent_executor or DefaultAgentExecutor()

    async def run(
        self,
        task: str,
        *,
        progress: ProgressCallback | None = None,
        stream: bool = True,
    ) -> OrchestrationResult:
        events: list[OrchestrationEvent] = []

        async def emit(stage: str, kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
            event = OrchestrationEvent(stage, kind, message, payload or {})
            events.append(event)
            if progress:
                result = progress(event)
                if isawaitable(result):
                    await result

        await emit("input", "received", "User task received", {"task": task})

        plugin_state = await self._load_plugins(task)
        await emit("plugins", "loaded", "Plugins routed and loaded", plugin_state)

        memory_route = await self._retrieve_memory(task)
        memory_payload = memory_route.to_dict()
        await emit("memory", "retrieved", "Memory routed and merged", memory_payload)

        security_result = await asyncio.to_thread(
            self.security.process,
            task,
            [self._memory_item_for_security(item) for item in memory_route.context],
        )
        security_payload = security_result.report()
        context_payload = security_payload.get("context")
        if isinstance(context_payload, Mapping):
            for key in ("instruction_context", "data_context", "blocked_context"):
                if key in context_payload:
                    security_payload[key] = context_payload[key]
        await emit("security", "validated", "Context sanitized and isolated", security_payload)

        runtime_context = self._runtime_context(task, plugin_state, memory_payload, security_payload)
        await emit("runtime", "prepared", "Runtime context prepared", {"keys": sorted(runtime_context)})

        agent_result = await self._execute_agent(task, runtime_context)
        await emit("agent", "completed", "Agent loop completed", agent_result)

        answer = self._answer(agent_result)
        if not answer:
            answer = "I could not produce an approved answer from the available routed memory and skills."
        accepted = bool(agent_result.get("accepted", bool(answer)))
        if stream and answer:
            for token in self._tokens(answer):
                await emit("output", "token", token, {"token": token})
        await emit("output", "final", "Final answer ready", {"answer": answer, "accepted": accepted})

        return OrchestrationResult(
            task=task,
            answer=answer,
            accepted=accepted,
            events=tuple(events),
            plugins=plugin_state,
            memory=memory_payload,
            security=security_payload,
            agent=agent_result,
        )

    async def stream(self, task: str) -> AsyncIterator[OrchestrationEvent]:
        queue: asyncio.Queue[OrchestrationEvent | None] = asyncio.Queue()

        async def progress(event: OrchestrationEvent) -> None:
            await queue.put(event)

        async def runner() -> None:
            try:
                await self.run(task, progress=progress, stream=True)
            finally:
                await queue.put(None)

        worker = asyncio.create_task(runner())
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
        await worker

    async def _load_plugins(self, task: str) -> dict[str, Any]:
        return await asyncio.to_thread(self.plugin_manager.resolve, task)

    async def _retrieve_memory(self, task: str) -> Any:
        return await asyncio.to_thread(self.memory_router.route, task)

    async def _execute_agent(self, task: str, context: Mapping[str, Any]) -> dict[str, Any]:
        def run() -> Mapping[str, Any]:
            executor = self.agent_executor
            if callable(executor) and not hasattr(executor, "run"):
                return executor(task, context)
            return executor.run(task, context)  # type: ignore[union-attr]

        result = await asyncio.to_thread(run)
        return dict(result)

    def _runtime_context(
        self,
        task: str,
        plugins: dict[str, Any],
        memory: dict[str, Any],
        security: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "task": task,
            "plugins": plugins,
            "memory": memory,
            "security": security,
            "skill_runtime": self.skill_runtime.__class__.__name__,
        }

    def _memory_item_for_security(self, item: Any) -> dict[str, Any]:
        payload = dict(getattr(item, "metadata", {}) or {})
        payload["text"] = str(getattr(item, "content", ""))
        payload["source"] = str(getattr(item, "source", "unknown"))
        return payload

    def _answer(self, agent_result: Mapping[str, Any]) -> str:
        for key in ("answer", "final_response", "final_output", "result"):
            value = agent_result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _tokens(self, text: str) -> list[str]:
        return [part for part in text.split(" ") if part] if text else []


def event_to_dict(event: OrchestrationEvent) -> dict[str, Any]:
    return asdict(event)


__all__ = [
    "AgentExecutor",
    "AnubisOrchestrationEngine",
    "ContextToolAdapter",
    "DefaultAgentExecutor",
    "OrchestrationEvent",
    "OrchestrationResult",
    "event_to_dict",
]
