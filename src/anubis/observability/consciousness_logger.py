"""Structured logs for internal state."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from anubis.types import utcnow


@dataclass(frozen=True, slots=True)
class LogRecord:
    level: str
    message: str
    component: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    timestamp: object = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class ConsciousnessLogger:
    def __init__(self) -> None:
        self.records: list[LogRecord] = []

    def log(self, level: str, message: str, *, component: str = "anubis", **metadata: Any) -> LogRecord:
        record = LogRecord(level=level, message=message, component=component, metadata=metadata)
        self.records.append(record)
        return record

