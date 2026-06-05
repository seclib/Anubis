from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4


def utcnow() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    PENDING = "pending"
    ROUTED = "routed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStatus(StrEnum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class EventType(StrEnum):
    TASK_SUBMITTED = "task.submitted"
    TASK_ROUTED = "task.routed"
    TASK_STARTED = "task.started"
    TASK_SUCCEEDED = "task.succeeded"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    EXECUTION_ATTEMPT_STARTED = "execution.attempt.started"
    EXECUTION_ATTEMPT_FAILED = "execution.attempt.failed"
    EXECUTION_RETRY_SCHEDULED = "execution.retry.scheduled"
    EXECUTION_ROLLBACK_STARTED = "execution.rollback.started"
    EXECUTION_ROLLBACK_SUCCEEDED = "execution.rollback.succeeded"
    EXECUTION_ROLLBACK_FAILED = "execution.rollback.failed"
    SANDBOX_ALLOWED = "sandbox.allowed"
    SANDBOX_DENIED = "sandbox.denied"
    SAFETY_ANOMALY_DETECTED = "safety.anomaly.detected"
    SAFETY_AGENT_SCORE_UPDATED = "safety.agent_score.updated"
    SAFETY_KILL_SWITCH_TRIGGERED = "safety.kill_switch.triggered"
    AGENT_REGISTERED = "agent.registered"
    AGENT_SPAWNED = "agent.spawned"
    AGENT_STOPPED = "agent.stopped"


@dataclass(frozen=True, slots=True)
class Task:
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    priority: int = 100
    id: str = field(default_factory=lambda: f"task_{uuid4().hex}")
    correlation_id: str = field(default_factory=lambda: f"corr_{uuid4().hex}")
    created_at: datetime = field(default_factory=utcnow)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        object.__setattr__(
            self,
            "required_capabilities",
            frozenset(self.required_capabilities),
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class TaskResult:
    task_id: str
    status: TaskStatus
    output: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None
    completed_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output", MappingProxyType(dict(self.output)))


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    name: str
    capabilities: frozenset[str]
    max_concurrency: int = 1
    version: str = "0.1.0"

    def __post_init__(self) -> None:
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    output: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output", MappingProxyType(dict(self.output)))


@dataclass(frozen=True, slots=True)
class Event:
    type: EventType
    producer: str
    payload: Mapping[str, Any]
    id: str = field(default_factory=lambda: f"evt_{uuid4().hex}")
    correlation_id: str | None = None
    task_id: str | None = None
    agent_name: str | None = None
    timestamp: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
