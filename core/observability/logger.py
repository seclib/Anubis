"""Structured JSON logging for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from json import dumps
from types import MappingProxyType
from typing import Any, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class LogRecord:
    sequence: int
    level: LogLevel
    component: str
    action: str
    message: str
    trace_id: str
    span_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        for field_name in ("component", "action", "message", "trace_id"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} cannot be empty")
            object.__setattr__(self, field_name, str(getattr(self, field_name)).strip())
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "component": self.component,
            "action": self.action,
            "message": self.message,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "metadata": dict(self.metadata),
        }

    def to_json(self) -> str:
        return dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


class StructuredLogger:
    """Append-only in-memory structured logger."""

    def __init__(self) -> None:
        self._records: list[LogRecord] = []

    def log(
        self,
        *,
        level: LogLevel | str,
        component: str,
        action: str,
        message: str,
        trace_id: str,
        span_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LogRecord:
        record = LogRecord(
            sequence=len(self._records) + 1,
            level=LogLevel(level),
            component=component,
            action=action,
            message=message,
            trace_id=trace_id,
            span_id=span_id,
            metadata=metadata or {},
        )
        self._records.append(record)
        return record

    def info(self, **kwargs: Any) -> LogRecord:
        return self.log(level=LogLevel.INFO, **kwargs)

    def error(
        self,
        *,
        component: str,
        action: str,
        message: str,
        trace_id: str,
        span_id: str | None = None,
        error: BaseException | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LogRecord:
        payload = dict(metadata or {})
        if error is not None:
            payload["error"] = {
                "type": error.__class__.__name__,
                "message": str(error),
            }
        return self.log(
            level=LogLevel.ERROR,
            component=component,
            action=action,
            message=message,
            trace_id=trace_id,
            span_id=span_id,
            metadata=payload,
        )

    def records(self) -> tuple[LogRecord, ...]:
        return tuple(self._records)

    def json_lines(self) -> tuple[str, ...]:
        return tuple(record.to_json() for record in self._records)


ConsciousnessLogger = StructuredLogger


__all__ = ["ConsciousnessLogger", "LogLevel", "LogRecord", "StructuredLogger"]
