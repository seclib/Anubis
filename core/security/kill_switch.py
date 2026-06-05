"""Kill switch state machine for ANUBIS security shutdowns."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


class KillSwitchReason(StrEnum):
    POLICY_VIOLATION = "policy_violation"
    SANDBOX_ESCAPE_ATTEMPT = "sandbox_escape_attempt"
    REPEATED_DENIALS = "repeated_denials"
    MANUAL_SECURITY_STOP = "manual_security_stop"


@dataclass(frozen=True, slots=True)
class KillSwitchEvent:
    sequence: int
    reason: KillSwitchReason
    triggered_by: str
    detail: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        if not self.triggered_by.strip():
            raise ValueError("triggered_by cannot be empty")
        if not self.detail.strip():
            raise ValueError("detail cannot be empty")
        object.__setattr__(self, "triggered_by", self.triggered_by.strip())
        object.__setattr__(self, "detail", self.detail.strip())
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "detail": self.detail,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class KillSwitchDecision:
    active: bool
    allowed: bool
    reason: str
    event: KillSwitchEvent | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "allowed": self.allowed,
            "reason": self.reason,
            "event": None if self.event is None else self.event.to_dict(),
        }


class KillSwitch:
    """One-way security stop. No reset API is provided by design."""

    _allowed_when_active = frozenset({"security.status.read", "audit.read"})

    def __init__(self) -> None:
        self._events: list[KillSwitchEvent] = []

    @property
    def active(self) -> bool:
        return bool(self._events)

    @property
    def event(self) -> KillSwitchEvent | None:
        return self._events[-1] if self._events else None

    def trigger(
        self,
        *,
        reason: KillSwitchReason,
        triggered_by: str,
        detail: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> KillSwitchEvent:
        event = KillSwitchEvent(
            sequence=len(self._events) + 1,
            reason=reason,
            triggered_by=triggered_by,
            detail=detail,
            metadata=metadata or {},
        )
        self._events.append(event)
        return event

    def validate_action(self, action: str) -> KillSwitchDecision:
        if not self.active:
            return KillSwitchDecision(
                active=False,
                allowed=True,
                reason="Kill switch is inactive.",
            )
        if action in self._allowed_when_active:
            return KillSwitchDecision(
                active=True,
                allowed=True,
                reason="Read-only security action allowed while kill switch is active.",
                event=self.event,
            )
        return KillSwitchDecision(
            active=True,
            allowed=False,
            reason="Kill switch active: action blocked.",
            event=self.event,
        )

    def events(self) -> tuple[KillSwitchEvent, ...]:
        return tuple(self._events)


__all__ = [
    "KillSwitch",
    "KillSwitchDecision",
    "KillSwitchEvent",
    "KillSwitchReason",
]
