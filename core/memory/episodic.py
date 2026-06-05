"""Append-only episodic memory for ANUBIS execution logs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True, slots=True)
class EpisodicMemoryRecord:
    """A single immutable execution event retained for traceability."""

    sequence: int
    event_type: str
    actor: str
    summary: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)
    record_id: str = ""

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        event_type = self.event_type.strip()
        actor = self.actor.strip()
        summary = self.summary.strip()
        if not event_type:
            raise ValueError("event_type cannot be empty")
        if not actor:
            raise ValueError("actor cannot be empty")
        if not summary:
            raise ValueError("summary cannot be empty")
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "actor", actor)
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))
        if not self.record_id:
            object.__setattr__(self, "record_id", f"episode_{self.sequence:08d}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "actor": self.actor,
            "summary": self.summary,
            "payload": dict(self.payload),
            "timestamp": self.timestamp.isoformat(),
        }


class EpisodicMemory:
    """Append-only store for runtime events and execution logs."""

    def __init__(self) -> None:
        self._records: list[EpisodicMemoryRecord] = []

    def append(
        self,
        *,
        event_type: str,
        actor: str,
        summary: str,
        payload: Mapping[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> EpisodicMemoryRecord:
        record = EpisodicMemoryRecord(
            sequence=len(self._records) + 1,
            event_type=event_type,
            actor=actor,
            summary=summary,
            payload=payload or {},
            timestamp=timestamp or _utcnow(),
        )
        self._records.append(record)
        return record

    def all(self) -> tuple[EpisodicMemoryRecord, ...]:
        return tuple(self._records)

    def recent(self, limit: int = 10) -> tuple[EpisodicMemoryRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        return tuple(self._records[-limit:])

    def query(
        self,
        *,
        event_type: str | None = None,
        actor: str | None = None,
        limit: int | None = None,
    ) -> tuple[EpisodicMemoryRecord, ...]:
        records = self._records
        if event_type is not None:
            records = [record for record in records if record.event_type == event_type]
        if actor is not None:
            records = [record for record in records if record.actor == actor]
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be at least 1")
            records = records[-limit:]
        return tuple(records)


__all__ = ["EpisodicMemory", "EpisodicMemoryRecord"]
