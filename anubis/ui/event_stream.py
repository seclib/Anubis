from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

SWARM_EVENTS = {
    "agent_started",
    "agent_progress",
    "agent_completed",
    "swarm_started",
    "swarm_completed",
}


@dataclass(frozen=True)
class Event:
    type: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


EventHandler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[EventHandler] = []
        self.events: list[Event] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._subscribers.append(handler)

    def emit(self, event_type: str, payload: dict[str, Any]) -> Event:
        event = Event(type=event_type, payload=dict(payload))
        self.events.append(event)
        for handler in tuple(self._subscribers):
            handler(event)
        return event


def emit(event_type: str, payload: dict[str, Any], bus: EventBus | None = None) -> Event:
    target = bus or default_event_bus()
    return target.emit(event_type, payload)


_DEFAULT_EVENT_BUS = EventBus()


def default_event_bus() -> EventBus:
    return _DEFAULT_EVENT_BUS


__all__ = ["Event", "EventBus", "EventHandler", "SWARM_EVENTS", "default_event_bus", "emit"]
