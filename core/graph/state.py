"""State containers for ANUBIS graph execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


class GraphRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class NodeRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class GraphError:
    node: str
    error_type: str
    message: str
    recoverable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "error_type": self.error_type,
            "message": self.message,
            "recoverable": self.recoverable,
        }


@dataclass(frozen=True, slots=True)
class NodeTrace:
    sequence: int
    node: str
    status: NodeRunStatus
    input_keys: tuple[str, ...]
    output_keys: tuple[str, ...]
    explanation: str
    started_at: datetime
    completed_at: datetime
    error: GraphError | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "node": self.node,
            "status": self.status.value,
            "input_keys": self.input_keys,
            "output_keys": self.output_keys,
            "explanation": self.explanation,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "error": None if self.error is None else self.error.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GraphState:
    """Immutable state passed between graph nodes.

    Nodes never mutate this object in-place. Each node returns a new state via
    ``with_updates`` so transitions remain explicit and traceable.
    """

    run_id: str
    stimulus: str
    source: str = "operator"
    context: Mapping[str, Any] = field(default_factory=dict)
    status: GraphRunStatus = GraphRunStatus.PENDING
    intent: Mapping[str, Any] = field(default_factory=dict)
    plan: Mapping[str, Any] = field(default_factory=dict)
    assignments: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    agent_results: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    sandbox_results: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    memory: Mapping[str, Any] = field(default_factory=dict)
    reflection: Mapping[str, Any] = field(default_factory=dict)
    output: Mapping[str, Any] = field(default_factory=dict)
    execution_path: tuple[str, ...] = field(default_factory=tuple)
    traces: tuple[NodeTrace, ...] = field(default_factory=tuple)
    errors: tuple[GraphError, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "stimulus", self.stimulus.strip())
        object.__setattr__(self, "source", self.source.strip() or "operator")
        object.__setattr__(self, "context", freeze_mapping(self.context))
        object.__setattr__(self, "intent", freeze_mapping(self.intent))
        object.__setattr__(self, "plan", freeze_mapping(self.plan))
        object.__setattr__(self, "assignments", tuple(freeze_mapping(item) for item in self.assignments))
        object.__setattr__(
            self,
            "agent_results",
            tuple(freeze_mapping(item) for item in self.agent_results),
        )
        object.__setattr__(
            self,
            "sandbox_results",
            tuple(freeze_mapping(item) for item in self.sandbox_results),
        )
        object.__setattr__(self, "memory", freeze_mapping(self.memory))
        object.__setattr__(self, "reflection", freeze_mapping(self.reflection))
        object.__setattr__(self, "output", freeze_mapping(self.output))
        object.__setattr__(self, "execution_path", tuple(self.execution_path))
        object.__setattr__(self, "traces", tuple(self.traces))
        object.__setattr__(self, "errors", tuple(self.errors))

    def with_updates(self, **updates: Any) -> "GraphState":
        updates["updated_at"] = utcnow()
        return replace(self, **updates)

    def append_trace(self, trace: NodeTrace) -> "GraphState":
        return self.with_updates(
            traces=(*self.traces, trace),
            execution_path=(*self.execution_path, trace.node),
        )

    def append_error(self, error: GraphError) -> "GraphState":
        return self.with_updates(errors=(*self.errors, error), status=GraphRunStatus.FAILED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "stimulus": self.stimulus,
            "source": self.source,
            "context": dict(self.context),
            "status": self.status.value,
            "intent": dict(self.intent),
            "plan": dict(self.plan),
            "assignments": tuple(dict(item) for item in self.assignments),
            "agent_results": tuple(dict(item) for item in self.agent_results),
            "sandbox_results": tuple(dict(item) for item in self.sandbox_results),
            "memory": dict(self.memory),
            "reflection": dict(self.reflection),
            "output": dict(self.output),
            "execution_path": self.execution_path,
            "traces": tuple(trace.to_dict() for trace in self.traces),
            "errors": tuple(error.to_dict() for error in self.errors),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


__all__ = [
    "GraphError",
    "GraphRunStatus",
    "GraphState",
    "NodeRunStatus",
    "NodeTrace",
    "freeze_mapping",
    "utcnow",
]
