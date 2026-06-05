from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

EventType = Literal[
    "session.started",
    "session.done",
    "assistant.token",
    "agent.state",
    "agent.message",
    "model.routed",
    "memory.retrieved",
    "memory.stored",
    "tool.request",
    "tool.result",
    "tool.error",
    "routing.decision",
    "guardrail.triggered",
    "error",
]


@dataclass(frozen=True)
class SessionEvent:
    type: EventType
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "type": self.type,
            "message": self.message,
            "payload": self.payload,
        }


__all__ = ["EventType", "SessionEvent"]
