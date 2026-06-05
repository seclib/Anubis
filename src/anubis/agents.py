from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from anubis.execution import RollbackHandler
from anubis.types import AgentDescriptor, AgentRunResult, Task

AgentHandler = Callable[[Task], Awaitable[AgentRunResult]]


@dataclass(slots=True)
class AgentRuntime:
    descriptor: AgentDescriptor
    handler: AgentHandler
    rollback_handler: RollbackHandler | None = None
    active_tasks: set[str] = field(default_factory=set)

    @property
    def available_capacity(self) -> int:
        return self.descriptor.max_concurrency - len(self.active_tasks)

    def can_run(self, task: Task) -> bool:
        return (
            task.required_capabilities.issubset(self.descriptor.capabilities)
            and self.available_capacity > 0
        )


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentRuntime] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        descriptor: AgentDescriptor,
        handler: AgentHandler,
        rollback_handler: RollbackHandler | None = None,
    ) -> None:
        async with self._lock:
            if descriptor.name in self._agents:
                raise ValueError(f"agent already registered: {descriptor.name}")
            self._agents[descriptor.name] = AgentRuntime(
                descriptor=descriptor,
                handler=handler,
                rollback_handler=rollback_handler,
            )

    async def select(self, task: Task) -> AgentRuntime:
        async with self._lock:
            preferred_agent = task.metadata.get("assigned_agent")
            if isinstance(preferred_agent, str):
                agent = self._agents.get(preferred_agent)
                if agent is None:
                    raise LookupError(f"assigned agent is not registered: {preferred_agent}")
                if not agent.can_run(task):
                    raise LookupError(f"assigned agent cannot run task: {preferred_agent}")
                return agent

            candidates = [agent for agent in self._agents.values() if agent.can_run(task)]
            if not candidates:
                raise LookupError(
                    "no available agent for capabilities: "
                    + ", ".join(sorted(task.required_capabilities))
                )
            return sorted(
                candidates,
                key=lambda agent: (-agent.available_capacity, agent.descriptor.name),
            )[0]

    async def mark_started(self, agent_name: str, task_id: str) -> frozenset[str]:
        async with self._lock:
            agent = self._agents[agent_name]
            if agent.available_capacity < 1:
                raise RuntimeError(f"agent has no capacity: {agent_name}")
            agent.active_tasks.add(task_id)
            return frozenset(agent.active_tasks)

    async def mark_finished(self, agent_name: str, task_id: str) -> frozenset[str]:
        async with self._lock:
            agent = self._agents[agent_name]
            agent.active_tasks.discard(task_id)
            return frozenset(agent.active_tasks)

    async def get(self, agent_name: str) -> AgentRuntime:
        async with self._lock:
            return self._agents[agent_name]

    async def descriptors(self) -> tuple[AgentDescriptor, ...]:
        async with self._lock:
            return tuple(
                sorted(
                    (agent.descriptor for agent in self._agents.values()),
                    key=lambda descriptor: descriptor.name,
                )
            )
