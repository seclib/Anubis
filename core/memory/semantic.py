"""Append-only semantic memory for structured ANUBIS knowledge."""

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
class SemanticMemoryRecord:
    """Immutable structured fact or knowledge assertion."""

    sequence: int
    subject: str
    predicate: str
    value: str
    confidence: float = 1.0
    source: str = "system"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)
    record_id: str = ""
    supersedes: str | None = None

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        subject = self.subject.strip()
        predicate = self.predicate.strip()
        value = self.value.strip()
        source = self.source.strip()
        if not subject:
            raise ValueError("subject cannot be empty")
        if not predicate:
            raise ValueError("predicate cannot be empty")
        if not value:
            raise ValueError("value cannot be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "predicate", predicate)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "source", source or "system")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        if not self.record_id:
            object.__setattr__(self, "record_id", f"semantic_{self.sequence:08d}")

    @property
    def key(self) -> tuple[str, str]:
        return (self.subject, self.predicate)

    @property
    def text(self) -> str:
        metadata = " ".join(f"{key}:{value}" for key, value in sorted(self.metadata.items()))
        return f"{self.subject} {self.predicate} {self.value} {metadata}".strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "sequence": self.sequence,
            "subject": self.subject,
            "predicate": self.predicate,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp.isoformat(),
            "supersedes": self.supersedes,
        }


class SemanticMemory:
    """Append-only store for structured knowledge."""

    def __init__(self) -> None:
        self._records: list[SemanticMemoryRecord] = []

    def append_fact(
        self,
        *,
        subject: str,
        predicate: str,
        value: str,
        confidence: float = 1.0,
        source: str = "system",
        metadata: Mapping[str, Any] | None = None,
        supersedes: str | None = None,
        timestamp: datetime | None = None,
    ) -> SemanticMemoryRecord:
        if supersedes is not None and self.get(supersedes) is None:
            raise ValueError(f"supersedes record does not exist: {supersedes}")
        record = SemanticMemoryRecord(
            sequence=len(self._records) + 1,
            subject=subject,
            predicate=predicate,
            value=value,
            confidence=confidence,
            source=source,
            metadata=metadata or {},
            supersedes=supersedes,
            timestamp=timestamp or _utcnow(),
        )
        self._records.append(record)
        return record

    def get(self, record_id: str) -> SemanticMemoryRecord | None:
        for record in self._records:
            if record.record_id == record_id:
                return record
        return None

    def all(self) -> tuple[SemanticMemoryRecord, ...]:
        return tuple(self._records)

    def history(self, subject: str, predicate: str | None = None) -> tuple[SemanticMemoryRecord, ...]:
        subject = subject.strip()
        if predicate is not None:
            predicate = predicate.strip()
        return tuple(
            record
            for record in self._records
            if record.subject == subject and (predicate is None or record.predicate == predicate)
        )

    def latest(self, subject: str, predicate: str) -> SemanticMemoryRecord | None:
        records = self.history(subject, predicate)
        return records[-1] if records else None

    def query(
        self,
        *,
        subject: str | None = None,
        predicate: str | None = None,
        source: str | None = None,
    ) -> tuple[SemanticMemoryRecord, ...]:
        records = self._records
        if subject is not None:
            records = [record for record in records if record.subject == subject]
        if predicate is not None:
            records = [record for record in records if record.predicate == predicate]
        if source is not None:
            records = [record for record in records if record.source == source]
        return tuple(records)


__all__ = ["SemanticMemory", "SemanticMemoryRecord"]
