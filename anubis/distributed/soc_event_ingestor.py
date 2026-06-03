"""AI SOC event ingestion and streaming pipeline for ANUBIS."""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from anubis.distributed.audit_logger import AuditActionType, AuditRecord
from anubis.distributed.contracts import OrchestrationEvent
from anubis.distributed.execution_logger import ExecutionLogEntry
from anubis.distributed.filesystem_jail import FileAccessAuditEntry
from anubis.distributed.network_isolation import NetworkAuditEntry, NetworkRequest
from anubis.distributed.permission_manager import PermissionDecision
from anubis.distributed.sandbox_runtime import SandboxExecutionResult


class SOCEventType(StrEnum):
    AGENT_ACTION = "agent_action"
    TOOL_EXECUTION = "tool_execution"
    FILE_ACCESS = "file_access"
    NETWORK_REQUEST = "network_request"
    EXECUTION_STEP = "execution_step"
    SYSTEM_ERROR = "system_error"
    SECURITY_EVENT = "security_event"
    ORCHESTRATION_EVENT = "orchestration_event"


@dataclass(frozen=True)
class SOCEvent:
    timestamp: datetime
    agent_id: str
    task_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    sequence: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "sequence": self.sequence,
        }


class SOCIngestionError(ValueError):
    """Raised when an event cannot be normalized for SOC ingestion."""


class SOCEventSink(Protocol):
    def __call__(self, event: SOCEvent) -> None: ...


class SOCEventStore:
    """Append-only SOC event store with optional JSONL persistence."""

    def __init__(self, log_path: str | Path | None = None) -> None:
        self.log_path = Path(log_path).resolve() if log_path else None
        self._events: list[SOCEvent] = []
        self._sequence = 0
        self._lock = RLock()

    def append(self, event: SOCEvent) -> SOCEvent:
        with self._lock:
            self._sequence += 1
            stored = SOCEvent(
                timestamp=event.timestamp,
                agent_id=event.agent_id,
                task_id=event.task_id,
                event_type=event.event_type,
                payload=event.payload,
                sequence=self._sequence,
            )
            self._events.append(stored)
            if self.log_path is not None:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as event_file:
                    event_file.write(json.dumps(stored.to_dict(), sort_keys=True) + "\n")
            return stored

    def events(self) -> tuple[SOCEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def query(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        event_type: SOCEventType | str | None = None,
    ) -> tuple[SOCEvent, ...]:
        normalized_type = _event_type_value(event_type) if event_type is not None else None
        with self._lock:
            return tuple(
                event
                for event in self._events
                if (task_id is None or event.task_id == task_id)
                and (agent_id is None or event.agent_id == agent_id)
                and (normalized_type is None or event.event_type == normalized_type)
            )


class SOCEventNormalizer:
    """Transforms all ANUBIS telemetry into the SOC normalized event shape."""

    def normalize(
        self,
        raw_event: Any,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        event_type: SOCEventType | str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> SOCEvent:
        if isinstance(raw_event, SOCEvent):
            return raw_event
        if isinstance(raw_event, AuditRecord):
            return self.from_audit_record(raw_event)
        if isinstance(raw_event, FileAccessAuditEntry):
            return self.from_file_access(raw_event, agent_id=agent_id)
        if isinstance(raw_event, NetworkAuditEntry):
            return self.from_network_audit(raw_event, agent_id=agent_id)
        if isinstance(raw_event, NetworkRequest):
            return self.from_network_request(raw_event, agent_id=agent_id)
        if isinstance(raw_event, ExecutionLogEntry):
            return self.from_execution_log(raw_event, agent_id=agent_id, task_id=task_id)
        if isinstance(raw_event, PermissionDecision):
            return self.from_permission_decision(raw_event, task_id=task_id)
        if isinstance(raw_event, SandboxExecutionResult):
            return self.from_sandbox_result(raw_event, agent_id=agent_id, task_id=task_id)
        if isinstance(raw_event, OrchestrationEvent):
            return self.from_orchestration_event(raw_event)
        if isinstance(raw_event, BaseException):
            return self.from_error(raw_event, agent_id=agent_id, task_id=task_id)
        if isinstance(raw_event, dict):
            return self.from_dict(raw_event, agent_id=agent_id, task_id=task_id, event_type=event_type, payload=payload)
        raise SOCIngestionError(f"unsupported SOC event source: {type(raw_event).__name__}")

    def from_audit_record(self, record: AuditRecord) -> SOCEvent:
        return SOCEvent(
            timestamp=record.timestamp,
            agent_id=record.agent_id,
            task_id=record.task_id,
            event_type=_audit_action_to_soc_type(record.action_type),
            payload=record.to_dict(),
        )

    def from_file_access(self, entry: FileAccessAuditEntry, *, agent_id: str | None = None) -> SOCEvent:
        return SOCEvent(
            timestamp=entry.created_at,
            agent_id=_identity(agent_id, "filesystem-jail"),
            task_id=entry.task_id,
            event_type=SOCEventType.FILE_ACCESS.value,
            payload=entry.to_dict(),
        )

    def from_network_audit(self, entry: NetworkAuditEntry, *, agent_id: str | None = None) -> SOCEvent:
        return SOCEvent(
            timestamp=entry.created_at,
            agent_id=_identity(agent_id, "network-proxy"),
            task_id=entry.task_id,
            event_type=SOCEventType.NETWORK_REQUEST.value,
            payload=entry.to_dict(),
        )

    def from_network_request(self, request: NetworkRequest, *, agent_id: str | None = None) -> SOCEvent:
        return SOCEvent(
            timestamp=_now(),
            agent_id=_identity(agent_id, "network-proxy"),
            task_id=request.task_id,
            event_type=SOCEventType.NETWORK_REQUEST.value,
            payload=request.to_dict(),
        )

    def from_execution_log(self, entry: ExecutionLogEntry, *, agent_id: str | None = None, task_id: str | None = None) -> SOCEvent:
        return SOCEvent(
            timestamp=_parse_datetime(entry.created_at),
            agent_id=_identity(agent_id, "executor"),
            task_id=_identity(task_id, entry.step_id),
            event_type=SOCEventType.TOOL_EXECUTION.value,
            payload={
                "step_id": entry.step_id,
                "tool": entry.tool,
                "success": entry.success,
                "message": entry.message,
                "metadata": dict(entry.metadata),
                "created_at": entry.created_at,
            },
        )

    def from_permission_decision(self, decision: PermissionDecision, *, task_id: str | None = None) -> SOCEvent:
        return SOCEvent(
            timestamp=_now(),
            agent_id=decision.agent_type,
            task_id=_identity(task_id, "unknown-task"),
            event_type=SOCEventType.SECURITY_EVENT.value,
            payload=decision.to_dict(),
        )

    def from_sandbox_result(self, result: SandboxExecutionResult, *, agent_id: str | None = None, task_id: str | None = None) -> SOCEvent:
        return SOCEvent(
            timestamp=_now(),
            agent_id=_identity(agent_id, "sandbox-runtime"),
            task_id=_identity(task_id, result.sandbox_id or "unknown-task"),
            event_type=SOCEventType.TOOL_EXECUTION.value,
            payload=result.to_dict(),
        )

    def from_orchestration_event(self, event: OrchestrationEvent) -> SOCEvent:
        return SOCEvent(
            timestamp=event.created_at,
            agent_id=event.agent_id or "orchestrator",
            task_id=event.task_id,
            event_type=SOCEventType.ORCHESTRATION_EVENT.value,
            payload={
                "event_type": event.event_type.value,
                "message": event.message,
                "subtask_id": event.subtask_id,
                "assignment_id": event.assignment_id,
                "agent_id": event.agent_id,
                "payload": dict(event.payload),
                "created_at": event.created_at.isoformat(),
            },
        )

    def from_error(self, error: BaseException, *, agent_id: str | None = None, task_id: str | None = None) -> SOCEvent:
        return SOCEvent(
            timestamp=_now(),
            agent_id=_identity(agent_id, "system"),
            task_id=_identity(task_id, "unknown-task"),
            event_type=SOCEventType.SYSTEM_ERROR.value,
            payload={
                "error_type": type(error).__name__,
                "message": str(error),
                "traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__)),
            },
        )

    def from_dict(
        self,
        event: dict[str, Any],
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        event_type: SOCEventType | str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> SOCEvent:
        raw_payload = dict(payload if payload is not None else event.get("payload", event))
        return SOCEvent(
            timestamp=_parse_datetime(event.get("timestamp")) if event.get("timestamp") else _now(),
            agent_id=_identity(agent_id or event.get("agent_id"), "unknown-agent"),
            task_id=_identity(task_id or event.get("task_id"), "unknown-task"),
            event_type=_event_type_value(event_type or event.get("event_type") or SOCEventType.AGENT_ACTION),
            payload=raw_payload,
        )


class SOCStreamingPipeline:
    """Real-time streaming fanout for normalized SOC events."""

    def __init__(self, *, max_workers: int = 8) -> None:
        self._subscribers: list[SOCEventSink] = []
        self._published: list[SOCEvent] = []
        self._pending: list[Future[Any]] = []
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="anubis-soc")
        self._lock = RLock()

    def subscribe(self, sink: SOCEventSink) -> None:
        if not callable(sink):
            raise ValueError("sink must be callable")
        with self._lock:
            self._subscribers.append(sink)

    def publish(self, event: SOCEvent) -> SOCEvent:
        with self._lock:
            self._published.append(event)
            subscribers = tuple(self._subscribers)
        for sink in subscribers:
            future = self._executor.submit(sink, event)
            with self._lock:
                self._pending.append(future)
        return event

    def drain(self, *, timeout: float | None = None) -> None:
        with self._lock:
            pending = tuple(self._pending)
            self._pending.clear()
        if pending:
            wait(pending, timeout=timeout)

    def published(self) -> tuple[SOCEvent, ...]:
        with self._lock:
            return tuple(self._published)

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


class CentralSOCEventCollector:
    """Mandatory intake point for all ANUBIS security and execution telemetry."""

    def __init__(
        self,
        *,
        normalizer: SOCEventNormalizer | None = None,
        store: SOCEventStore | None = None,
        pipeline: SOCStreamingPipeline | None = None,
    ) -> None:
        self.normalizer = normalizer or SOCEventNormalizer()
        self.store = store or SOCEventStore()
        self.pipeline = pipeline or SOCStreamingPipeline()

    def ingest(
        self,
        raw_event: Any,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        event_type: SOCEventType | str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> SOCEvent:
        normalized = self.normalizer.normalize(
            raw_event,
            agent_id=agent_id,
            task_id=task_id,
            event_type=event_type,
            payload=payload,
        )
        stored = self.store.append(normalized)
        self.pipeline.publish(stored)
        return stored

    def ingest_system_error(self, error: BaseException, *, agent_id: str = "system", task_id: str = "unknown-task") -> SOCEvent:
        return self.ingest(error, agent_id=agent_id, task_id=task_id)

    def events(self) -> tuple[SOCEvent, ...]:
        return self.store.events()

    def query(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        event_type: SOCEventType | str | None = None,
    ) -> tuple[SOCEvent, ...]:
        return self.store.query(task_id=task_id, agent_id=agent_id, event_type=event_type)


class SOCRequiredIngestionGate:
    """Small guard for components that must prove they emitted SOC telemetry."""

    def __init__(self, collector: CentralSOCEventCollector) -> None:
        self.collector = collector

    def ingest_or_raise(self, raw_event: Any, **kwargs: Any) -> SOCEvent:
        event = self.collector.ingest(raw_event, **kwargs)
        if event.sequence is None:
            raise SOCIngestionError("SOC event was not stored; execution telemetry cannot proceed")
        return event


def _audit_action_to_soc_type(action_type: AuditActionType) -> str:
    if action_type == AuditActionType.TOOL_CALL:
        return SOCEventType.TOOL_EXECUTION.value
    if action_type == AuditActionType.FILE_ACCESS:
        return SOCEventType.FILE_ACCESS.value
    if action_type == AuditActionType.NETWORK_ACCESS:
        return SOCEventType.NETWORK_REQUEST.value
    if action_type == AuditActionType.EXECUTION_STEP:
        return SOCEventType.EXECUTION_STEP.value
    if action_type == AuditActionType.SECURITY_EVENT:
        return SOCEventType.SECURITY_EVENT.value
    return SOCEventType.AGENT_ACTION.value


def _event_type_value(event_type: SOCEventType | str) -> str:
    if isinstance(event_type, SOCEventType):
        return event_type.value
    if not isinstance(event_type, str) or not event_type.strip():
        raise SOCIngestionError("event_type is required")
    try:
        return SOCEventType(event_type).value
    except ValueError:
        return event_type.strip()


def _identity(value: str | None, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


__all__ = [
    "CentralSOCEventCollector",
    "SOCEvent",
    "SOCEventNormalizer",
    "SOCEventSink",
    "SOCEventStore",
    "SOCEventType",
    "SOCIngestionError",
    "SOCRequiredIngestionGate",
    "SOCStreamingPipeline",
]
