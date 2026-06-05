from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from anubis.types import AgentStatus, Task, TaskResult, TaskStatus, utcnow


@dataclass(frozen=True, slots=True)
class TaskRecord:
    task: Task
    status: TaskStatus
    agent_name: str | None = None
    result: TaskResult | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, slots=True)
class AgentRecord:
    name: str
    status: AgentStatus
    active_tasks: frozenset[str] = field(default_factory=frozenset)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_tasks", frozenset(self.active_tasks))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class StateStore:
    async def put_task(self, task: Task, status: TaskStatus = TaskStatus.PENDING) -> None:
        raise NotImplementedError

    async def update_task(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        agent_name: str | None = None,
        result: TaskResult | None = None,
        error: str | None = None,
    ) -> None:
        raise NotImplementedError

    async def get_task(self, task_id: str) -> TaskRecord:
        raise NotImplementedError

    async def put_agent(self, name: str, status: AgentStatus) -> None:
        raise NotImplementedError

    async def update_agent(
        self,
        name: str,
        status: AgentStatus,
        *,
        active_tasks: frozenset[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        raise NotImplementedError

    async def get_agent(self, name: str) -> AgentRecord:
        raise NotImplementedError


class InMemoryStateStore(StateStore):
    """Thread-safe enough for a single asyncio process; replaceable with durable storage."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._agents: dict[str, AgentRecord] = {}
        self._lock = asyncio.Lock()

    async def put_task(self, task: Task, status: TaskStatus = TaskStatus.PENDING) -> None:
        async with self._lock:
            self._tasks[task.id] = TaskRecord(task=task, status=status)

    async def update_task(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        agent_name: str | None = None,
        result: TaskResult | None = None,
        error: str | None = None,
    ) -> None:
        async with self._lock:
            existing = self._tasks[task_id]
            self._tasks[task_id] = TaskRecord(
                task=existing.task,
                status=status,
                agent_name=agent_name if agent_name is not None else existing.agent_name,
                result=result if result is not None else existing.result,
                error=error if error is not None else existing.error,
                created_at=existing.created_at,
                updated_at=utcnow(),
            )

    async def get_task(self, task_id: str) -> TaskRecord:
        async with self._lock:
            return self._tasks[task_id]

    async def put_agent(self, name: str, status: AgentStatus) -> None:
        async with self._lock:
            self._agents[name] = AgentRecord(name=name, status=status)

    async def update_agent(
        self,
        name: str,
        status: AgentStatus,
        *,
        active_tasks: frozenset[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        async with self._lock:
            existing = self._agents[name]
            self._agents[name] = AgentRecord(
                name=name,
                status=status,
                active_tasks=(
                    active_tasks if active_tasks is not None else existing.active_tasks
                ),
                metadata=metadata if metadata is not None else existing.metadata,
                updated_at=utcnow(),
            )

    async def get_agent(self, name: str) -> AgentRecord:
        async with self._lock:
            return self._agents[name]

