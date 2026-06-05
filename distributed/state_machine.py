"""Persistent state machine for ANUBIS distributed task execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from threading import RLock
from typing import Any

from anubis.distributed.contracts import EventType, OrchestrationEvent, utc_now
from anubis.distributed.event_bus import EventBus
from anubis.distributed.state_persistence import InMemoryStatePersistence, StatePersistence
from anubis.distributed.transition_validator import DistributedTaskState, TransitionValidator


@dataclass(frozen=True)
class TaskStateRecord:
    task_id: str
    state: DistributedTaskState
    version: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    history: tuple[dict[str, Any], ...] = ()
    updated_at: str = field(default_factory=lambda: utc_now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "version": self.version,
            "metadata": dict(self.metadata),
            "history": [dict(item) for item in self.history],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskStateRecord":
        return cls(
            task_id=str(payload["task_id"]),
            state=DistributedTaskState(str(payload["state"])),
            version=int(payload.get("version", 0)),
            metadata=dict(payload.get("metadata", {}) or {}),
            history=tuple(dict(item) for item in payload.get("history", ()) if isinstance(item, dict)),
            updated_at=str(payload.get("updated_at") or utc_now().isoformat()),
        )


class StateMachineError(Exception):
    """Base error for state machine failures."""


class TaskStateNotFoundError(StateMachineError, KeyError):
    """Raised when a task state record cannot be found."""


class DistributedStateMachine:
    """Single source of truth for distributed task lifecycle state."""

    def __init__(
        self,
        *,
        persistence: StatePersistence | None = None,
        validator: TransitionValidator | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.persistence = persistence or InMemoryStatePersistence()
        self.validator = validator or TransitionValidator()
        self.event_bus = event_bus
        self._records: dict[str, TaskStateRecord] = {}
        self._lock = RLock()
        self.recover()

    def create_task(
        self,
        task_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> TaskStateRecord:
        normalized_id = task_id.strip()
        if not normalized_id:
            raise ValueError("task_id is required")
        with self._lock:
            existing = self._records.get(normalized_id)
            if existing is not None:
                return existing
            now = utc_now().isoformat()
            record = TaskStateRecord(
                task_id=normalized_id,
                state=DistributedTaskState.PENDING,
                metadata=metadata or {},
                history=(
                    {
                        "from": None,
                        "to": DistributedTaskState.PENDING.value,
                        "reason": "task created",
                        "created_at": now,
                    },
                ),
                updated_at=now,
            )
            self._save(record)
        self._publish_state_change(record, previous=None, reason="task created")
        return record

    def transition(
        self,
        task_id: str,
        target: DistributedTaskState | str,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> TaskStateRecord:
        target_state = DistributedTaskState(target)
        with self._lock:
            current = self._require(task_id)
            self.validator.validate(current.state, target_state)
            now = utc_now().isoformat()
            event = {
                "from": current.state.value,
                "to": target_state.value,
                "reason": reason,
                "created_at": now,
            }
            merged_metadata = dict(current.metadata)
            if metadata:
                merged_metadata.update(metadata)
            updated = replace(
                current,
                state=target_state,
                version=current.version + 1,
                metadata=merged_metadata,
                history=(*current.history, event),
                updated_at=now,
            )
            self._save(updated)
        self._publish_state_change(updated, previous=current.state, reason=reason)
        return updated

    def get(self, task_id: str) -> TaskStateRecord:
        with self._lock:
            return self._require(task_id)

    def recover(self) -> tuple[TaskStateRecord, ...]:
        records = tuple(TaskStateRecord.from_dict(payload) for payload in self.persistence.load_all())
        with self._lock:
            self._records = {record.task_id: record for record in records}
        return records

    def all_records(self) -> tuple[TaskStateRecord, ...]:
        with self._lock:
            return tuple(self._records[task_id] for task_id in sorted(self._records))

    def _require(self, task_id: str) -> TaskStateRecord:
        record = self._records.get(task_id)
        if record is None:
            payload = self.persistence.load(task_id)
            if payload is not None:
                record = TaskStateRecord.from_dict(payload)
                self._records[task_id] = record
        if record is None:
            raise TaskStateNotFoundError(f"Unknown task state: {task_id}")
        return record

    def _save(self, record: TaskStateRecord) -> None:
        self._records[record.task_id] = record
        self.persistence.save(record.task_id, record.to_dict())

    def _publish_state_change(
        self,
        record: TaskStateRecord,
        *,
        previous: DistributedTaskState | None,
        reason: str,
    ) -> None:
        if self.event_bus is None:
            return
        self.event_bus.publish(
            OrchestrationEvent(
                event_type=EventType.TASK_STATE_CHANGED,
                task_id=record.task_id,
                message=f"Task state changed to {record.state.value}",
                payload={
                    "task_id": record.task_id,
                    "from": previous.value if previous is not None else None,
                    "to": record.state.value,
                    "state": record.state.value,
                    "version": record.version,
                    "reason": reason,
                    "metadata": dict(record.metadata),
                },
            )
        )


__all__ = [
    "DistributedStateMachine",
    "StateMachineError",
    "TaskStateNotFoundError",
    "TaskStateRecord",
]
