"""Contracts for the ANUBIS distributed orchestration layer.

B1 defines coordination primitives only. These objects describe work, routing,
events, and worker availability; they do not execute tools or touch storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class AgentType(StrEnum):
    PLANNER = "planner"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"


class TaskStatus(StrEnum):
    CREATED = "created"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EventType(StrEnum):
    TASK_CREATED = "task_created"
    TASK_ASSIGNED = "task_assigned"
    TASK_STATE_CHANGED = "task_state_changed"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"


@dataclass(frozen=True)
class OrchestrationEvent:
    event_type: EventType
    task_id: str
    message: str
    subtask_id: str | None = None
    assignment_id: str | None = None
    agent_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class AgentRegistration:
    agent_id: str
    agent_type: AgentType
    endpoint: str | None = None
    max_concurrent: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    active_assignments: int = 0
    enabled: bool = True

    @property
    def available_capacity(self) -> int:
        if not self.enabled:
            return 0
        return max(0, self.max_concurrent - self.active_assignments)


@dataclass(frozen=True)
class Subtask:
    task_id: str
    subtask_id: str
    agent_type: AgentType
    objective: str
    dependencies: tuple[str, ...] = ()
    status: TaskStatus = TaskStatus.CREATED
    assigned_agent_id: str | None = None
    assignment_id: str | None = None
    attempts: int = 0
    max_retries: int = 2
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class TaskEnvelope:
    task_id: str
    objective: str
    status: TaskStatus = TaskStatus.CREATED
    subtasks: tuple[Subtask, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class AgentAssignment:
    assignment_id: str
    task_id: str
    subtask_id: str
    agent_id: str
    agent_type: AgentType
    objective: str
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class AgentResult:
    assignment_id: str
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


__all__ = [
    "AgentAssignment",
    "AgentRegistration",
    "AgentResult",
    "AgentType",
    "EventType",
    "OrchestrationEvent",
    "Subtask",
    "TaskEnvelope",
    "TaskStatus",
    "new_id",
    "utc_now",
]
