"""Rollback signaling for Reviewer Agent validation results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ReviewRecommendation(StrEnum):
    APPROVE = "approve"
    RETRY = "retry"
    ROLLBACK = "rollback"


@dataclass(frozen=True)
class RollbackSignal:
    step_id: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


class RollbackSignalCollector:
    """Collects rollback suggestions without executing rollback actions."""

    def __init__(self) -> None:
        self._signals: list[RollbackSignal] = []

    def emit(self, signal: RollbackSignal) -> RollbackSignal:
        self._signals.append(signal)
        return signal

    def signals(self) -> tuple[RollbackSignal, ...]:
        return tuple(self._signals)


__all__ = ["ReviewRecommendation", "RollbackSignal", "RollbackSignalCollector"]
