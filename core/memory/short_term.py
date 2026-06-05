"""Bounded short-term memory for active ANUBIS graph runs."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ShortTermMemoryRecord:
    sequence: int
    key: str
    value: Mapping[str, Any]
    actor: str = "system"
    timestamp: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        if not self.key.strip():
            raise ValueError("short-term key cannot be empty")
        object.__setattr__(self, "key", self.key.strip())
        object.__setattr__(self, "actor", self.actor.strip() or "system")
        object.__setattr__(self, "value", MappingProxyType(dict(self.value)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "key": self.key,
            "value": dict(self.value),
            "actor": self.actor,
            "timestamp": self.timestamp.isoformat(),
        }


class ShortTermMemory:
    """Volatile bounded memory; newest records evict oldest records deterministically."""

    def __init__(self, *, capacity: int = 100) -> None:
        if capacity < 1:
            raise ValueError("short-term memory capacity must be positive")
        self.capacity = capacity
        self._records: deque[ShortTermMemoryRecord] = deque(maxlen=capacity)
        self._next_sequence = 1

    def remember(
        self,
        *,
        key: str,
        value: Mapping[str, Any],
        actor: str = "system",
    ) -> ShortTermMemoryRecord:
        record = ShortTermMemoryRecord(
            sequence=self._next_sequence,
            key=key,
            value=value,
            actor=actor,
        )
        self._next_sequence += 1
        self._records.append(record)
        return record

    def recall(self, key: str | None = None, *, limit: int | None = None) -> tuple[ShortTermMemoryRecord, ...]:
        records = tuple(self._records)
        if key is not None:
            records = tuple(record for record in records if record.key == key)
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be positive")
            records = records[-limit:]
        return records

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": "short_term",
            "count": len(self._records),
            "capacity": self.capacity,
            "volatile": True,
        }


__all__ = ["ShortTermMemory", "ShortTermMemoryRecord"]
