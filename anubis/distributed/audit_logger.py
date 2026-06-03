"""Audit and observability backend for ANUBIS distributed agents."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditActionType(StrEnum):
    TOOL_CALL = "tool_call"
    FILE_ACCESS = "file_access"
    EXECUTION_STEP = "execution_step"
    AGENT_DECISION = "agent_decision"
    NETWORK_ACCESS = "network_access"
    SECURITY_EVENT = "security_event"


class AuditResult(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    INFO = "info"


@dataclass(frozen=True)
class AuditRecord:
    task_id: str
    agent_id: str
    action_type: AuditActionType
    result: AuditResult
    action: str
    details: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    step_id: str | None = None
    timestamp: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "action_type": self.action_type.value,
            "result": self.result.value,
            "action": self.action,
            "trace_id": self.trace_id,
            "step_id": self.step_id,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class TraceEvent:
    sequence: int
    record: AuditRecord

    def to_dict(self) -> dict[str, Any]:
        payload = self.record.to_dict()
        payload["sequence"] = self.sequence
        return payload


@dataclass(frozen=True)
class ExecutionTrace:
    trace_id: str
    task_id: str
    events: tuple[TraceEvent, ...]

    @property
    def started_at(self) -> datetime | None:
        return self.events[0].record.timestamp if self.events else None

    @property
    def ended_at(self) -> datetime | None:
        return self.events[-1].record.timestamp if self.events else None

    @property
    def failed(self) -> bool:
        return any(event.record.result in {AuditResult.FAILURE, AuditResult.DENIED} for event in self.events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "failed": self.failed,
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True)
class ObservabilitySummary:
    total_records: int
    total_tasks: int
    total_traces: int
    action_counts: dict[str, int]
    result_counts: dict[str, int]
    recent_records: tuple[AuditRecord, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "total_tasks": self.total_tasks,
            "total_traces": self.total_traces,
            "action_counts": dict(self.action_counts),
            "result_counts": dict(self.result_counts),
            "recent_records": [record.to_dict() for record in self.recent_records],
        }


class AuditLogStore:
    """Append-only structured audit log with optional JSONL persistence."""

    def __init__(self, log_path: str | Path | None = None) -> None:
        self.log_path = Path(log_path).resolve() if log_path else None
        self._records: list[AuditRecord] = []
        self._lock = RLock()

    def append(self, record: AuditRecord) -> AuditRecord:
        with self._lock:
            self._records.append(record)
            if self.log_path is not None:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as audit_file:
                    audit_file.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        return record

    def records(self) -> tuple[AuditRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def query(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        action_type: AuditActionType | str | None = None,
        result: AuditResult | str | None = None,
    ) -> tuple[AuditRecord, ...]:
        normalized_action = _normalize_action_type(action_type) if action_type is not None else None
        normalized_result = _normalize_result(result) if result is not None else None
        with self._lock:
            return tuple(
                record
                for record in self._records
                if (task_id is None or record.task_id == task_id)
                and (agent_id is None or record.agent_id == agent_id)
                and (normalized_action is None or record.action_type == normalized_action)
                and (normalized_result is None or record.result == normalized_result)
            )


class TraceRecorder:
    """Builds per-task execution traces from audit records."""

    def __init__(self) -> None:
        self._traces: dict[str, list[TraceEvent]] = {}
        self._task_to_trace: dict[str, str] = {}
        self._sequence = 0
        self._lock = RLock()

    def record(self, record: AuditRecord) -> TraceEvent:
        with self._lock:
            trace_id = record.trace_id or self._task_to_trace.get(record.task_id) or f"trace-{record.task_id}"
            self._task_to_trace[record.task_id] = trace_id
            if record.trace_id is None:
                record = AuditRecord(
                    task_id=record.task_id,
                    agent_id=record.agent_id,
                    action_type=record.action_type,
                    result=record.result,
                    action=record.action,
                    details=record.details,
                    trace_id=trace_id,
                    step_id=record.step_id,
                    timestamp=record.timestamp,
                )
            self._sequence += 1
            event = TraceEvent(sequence=self._sequence, record=record)
            self._traces.setdefault(trace_id, []).append(event)
            return event

    def trace_for_task(self, task_id: str) -> ExecutionTrace:
        with self._lock:
            trace_id = self._task_to_trace.get(task_id, f"trace-{task_id}")
            return ExecutionTrace(trace_id=trace_id, task_id=task_id, events=tuple(self._traces.get(trace_id, ())))

    def trace(self, trace_id: str) -> ExecutionTrace:
        with self._lock:
            events = tuple(self._traces.get(trace_id, ()))
            task_id = events[0].record.task_id if events else ""
            return ExecutionTrace(trace_id=trace_id, task_id=task_id, events=events)

    def traces(self) -> tuple[ExecutionTrace, ...]:
        with self._lock:
            return tuple(
                ExecutionTrace(trace_id=trace_id, task_id=events[0].record.task_id if events else "", events=tuple(events))
                for trace_id, events in sorted(self._traces.items())
            )


class AuditLogger:
    """Records every agent action as structured audit data and trace events."""

    def __init__(self, *, store: AuditLogStore | None = None, traces: TraceRecorder | None = None) -> None:
        self.store = store or AuditLogStore()
        self.traces = traces or TraceRecorder()

    def log(
        self,
        *,
        task_id: str,
        agent_id: str,
        action_type: AuditActionType | str,
        result: AuditResult | str | bool,
        action: str,
        details: dict[str, Any] | None = None,
        step_id: str | None = None,
        trace_id: str | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            task_id=_required(task_id, "task_id"),
            agent_id=_required(agent_id, "agent_id"),
            action_type=_normalize_action_type(action_type),
            result=_normalize_result(result),
            action=_required(action, "action"),
            details=dict(details or {}),
            trace_id=trace_id,
            step_id=step_id,
        )
        event = self.traces.record(record)
        return self.store.append(event.record)

    def log_tool_call(
        self,
        *,
        task_id: str,
        agent_id: str,
        tool: str,
        success: bool,
        step_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        return self.log(
            task_id=task_id,
            agent_id=agent_id,
            action_type=AuditActionType.TOOL_CALL,
            result=success,
            action=tool,
            step_id=step_id,
            details=details,
        )

    def log_file_access(
        self,
        *,
        task_id: str,
        agent_id: str,
        path: str,
        operation: str,
        allowed: bool,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        return self.log(
            task_id=task_id,
            agent_id=agent_id,
            action_type=AuditActionType.FILE_ACCESS,
            result=AuditResult.SUCCESS if allowed else AuditResult.DENIED,
            action=operation,
            details={"path": path, **dict(details or {})},
        )

    def log_execution_step(
        self,
        *,
        task_id: str,
        agent_id: str,
        step_id: str,
        action: str,
        success: bool,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        return self.log(
            task_id=task_id,
            agent_id=agent_id,
            action_type=AuditActionType.EXECUTION_STEP,
            result=success,
            action=action,
            step_id=step_id,
            details=details,
        )

    def log_agent_decision(
        self,
        *,
        task_id: str,
        agent_id: str,
        decision: str,
        result: AuditResult | str = AuditResult.INFO,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        return self.log(
            task_id=task_id,
            agent_id=agent_id,
            action_type=AuditActionType.AGENT_DECISION,
            result=result,
            action=decision,
            details=details,
        )

    def records(self) -> tuple[AuditRecord, ...]:
        return self.store.records()

    def trace_for_task(self, task_id: str) -> ExecutionTrace:
        return self.traces.trace_for_task(task_id)


class ObservabilityDashboardBackend:
    """Read-only backend API for dashboards, debugging, and compliance views."""

    def __init__(self, audit_logger: AuditLogger) -> None:
        self.audit_logger = audit_logger

    def task_trace(self, task_id: str) -> dict[str, Any]:
        return self.audit_logger.trace_for_task(task_id).to_dict()

    def records(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        action_type: AuditActionType | str | None = None,
        result: AuditResult | str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        return tuple(
            record.to_dict()
            for record in self.audit_logger.store.query(
                task_id=task_id,
                agent_id=agent_id,
                action_type=action_type,
                result=result,
            )
        )

    def summary(self, *, recent_limit: int = 10) -> ObservabilitySummary:
        records = self.audit_logger.records()
        action_counts: dict[str, int] = {}
        result_counts: dict[str, int] = {}
        for record in records:
            action_counts[record.action_type.value] = action_counts.get(record.action_type.value, 0) + 1
            result_counts[record.result.value] = result_counts.get(record.result.value, 0) + 1
        return ObservabilitySummary(
            total_records=len(records),
            total_tasks=len({record.task_id for record in records}),
            total_traces=len(self.audit_logger.traces.traces()),
            action_counts=action_counts,
            result_counts=result_counts,
            recent_records=tuple(records[-recent_limit:]),
        )


def _normalize_action_type(value: AuditActionType | str) -> AuditActionType:
    if isinstance(value, AuditActionType):
        return value
    return AuditActionType(value)


def _normalize_result(value: AuditResult | str | bool) -> AuditResult:
    if isinstance(value, AuditResult):
        return value
    if isinstance(value, bool):
        return AuditResult.SUCCESS if value else AuditResult.FAILURE
    return AuditResult(value)


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


__all__ = [
    "AuditActionType",
    "AuditLogStore",
    "AuditLogger",
    "AuditRecord",
    "AuditResult",
    "ExecutionTrace",
    "ObservabilityDashboardBackend",
    "ObservabilitySummary",
    "TraceEvent",
    "TraceRecorder",
]
