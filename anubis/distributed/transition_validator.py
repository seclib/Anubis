"""Transition validation for the ANUBIS task state machine."""

from __future__ import annotations

from enum import StrEnum


class DistributedTaskState(StrEnum):
    PENDING = "pending"
    PLANNED = "planned"
    EXECUTING = "executing"
    BLOCKED = "blocked"
    RETRYING = "retrying"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class InvalidStateTransitionError(ValueError):
    """Raised when a requested state transition is not allowed."""


class TransitionValidator:
    """Enforces legal task lifecycle transitions."""

    _ALLOWED: dict[DistributedTaskState, frozenset[DistributedTaskState]] = {
        DistributedTaskState.PENDING: frozenset(
            {
                DistributedTaskState.PLANNED,
                DistributedTaskState.BLOCKED,
                DistributedTaskState.FAILED,
            }
        ),
        DistributedTaskState.PLANNED: frozenset(
            {
                DistributedTaskState.EXECUTING,
                DistributedTaskState.BLOCKED,
                DistributedTaskState.FAILED,
            }
        ),
        DistributedTaskState.EXECUTING: frozenset(
            {
                DistributedTaskState.VERIFYING,
                DistributedTaskState.BLOCKED,
                DistributedTaskState.RETRYING,
                DistributedTaskState.FAILED,
            }
        ),
        DistributedTaskState.BLOCKED: frozenset(
            {
                DistributedTaskState.RETRYING,
                DistributedTaskState.FAILED,
            }
        ),
        DistributedTaskState.RETRYING: frozenset(
            {
                DistributedTaskState.EXECUTING,
                DistributedTaskState.BLOCKED,
                DistributedTaskState.FAILED,
            }
        ),
        DistributedTaskState.VERIFYING: frozenset(
            {
                DistributedTaskState.COMPLETED,
                DistributedTaskState.RETRYING,
                DistributedTaskState.BLOCKED,
                DistributedTaskState.FAILED,
            }
        ),
        DistributedTaskState.COMPLETED: frozenset(),
        DistributedTaskState.FAILED: frozenset(),
    }

    def validate(
        self,
        current: DistributedTaskState | str,
        target: DistributedTaskState | str,
    ) -> None:
        current_state = DistributedTaskState(current)
        target_state = DistributedTaskState(target)
        if target_state not in self._ALLOWED[current_state]:
            raise InvalidStateTransitionError(
                f"Invalid task state transition: {current_state.value} -> {target_state.value}"
            )

    def allowed_targets(self, state: DistributedTaskState | str) -> tuple[DistributedTaskState, ...]:
        return tuple(sorted(self._ALLOWED[DistributedTaskState(state)], key=lambda item: item.value))


__all__ = [
    "DistributedTaskState",
    "InvalidStateTransitionError",
    "TransitionValidator",
]
