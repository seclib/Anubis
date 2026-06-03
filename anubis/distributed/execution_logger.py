"""Execution logging primitives for the distributed Executor Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ExecutionLogEntry:
    step_id: str
    tool: str
    success: bool
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    def to_log_line(self) -> str:
        status = "success" if self.success else "failure"
        return f"{self.created_at} [{status}] {self.step_id} {self.tool}: {self.message}"


class InMemoryExecutionLogger:
    """Process-local logger for tests and simple worker deployments."""

    def __init__(self) -> None:
        self._entries: list[ExecutionLogEntry] = []
        self._lock = RLock()

    def record(self, entry: ExecutionLogEntry) -> ExecutionLogEntry:
        with self._lock:
            self._entries.append(entry)
        return entry

    def entries(self) -> tuple[ExecutionLogEntry, ...]:
        with self._lock:
            return tuple(self._entries)


__all__ = ["ExecutionLogEntry", "InMemoryExecutionLogger"]
