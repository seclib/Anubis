"""Versioned immutable state engine for ANUBIS graph execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha256
from json import dumps
from types import MappingProxyType
from typing import Any, Mapping

from core.graph.state import GraphState, freeze_mapping, utcnow


def _canonical(value: Mapping[str, Any]) -> str:
    return dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash_payload(value: Mapping[str, Any]) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _freeze_run_states(value: Mapping[str, GraphState] | None) -> Mapping[str, GraphState]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True, slots=True)
class StateTransition:
    """Traceable description of one immutable state replacement."""

    sequence: int
    run_id: str
    actor: str
    action: str
    from_version: int
    to_version: int
    reason: str
    changed_fields: tuple[str, ...]
    before_hash: str
    after_hash: str
    timestamp: object = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("transition sequence must be positive")
        if self.to_version <= self.from_version:
            raise ValueError("transition to_version must be greater than from_version")
        for name in ("run_id", "actor", "action", "reason", "before_hash", "after_hash"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"transition {name} cannot be empty")
            object.__setattr__(self, name, str(getattr(self, name)).strip())
        object.__setattr__(self, "changed_fields", tuple(sorted(self.changed_fields)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "run_id": self.run_id,
            "actor": self.actor,
            "action": self.action,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "reason": self.reason,
            "changed_fields": self.changed_fields,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "timestamp": str(self.timestamp),
        }


@dataclass(frozen=True, slots=True)
class StateVersion:
    """Immutable snapshot of global system state at one version."""

    version: int
    state_hash: str
    run_id: str
    state: GraphState
    transition: StateTransition | None = None
    timestamp: object = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if self.version < 0:
            raise ValueError("state version cannot be negative")
        if not self.state_hash.strip():
            raise ValueError("state_hash cannot be empty")
        if not self.run_id.strip():
            raise ValueError("run_id cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "state_hash": self.state_hash,
            "run_id": self.run_id,
            "state": self.state.to_dict(),
            "transition": None if self.transition is None else self.transition.to_dict(),
            "timestamp": str(self.timestamp),
        }


@dataclass(frozen=True, slots=True)
class GlobalSystemState:
    """Global immutable state object for all ANUBIS graph runs."""

    version: int = 0
    run_states: Mapping[str, GraphState] = field(default_factory=dict)
    history: tuple[StateVersion, ...] = field(default_factory=tuple)
    transitions: tuple[StateTransition, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: object = field(default_factory=utcnow)
    updated_at: object = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if self.version < 0:
            raise ValueError("global state version cannot be negative")
        object.__setattr__(self, "run_states", _freeze_run_states(self.run_states))
        object.__setattr__(self, "history", tuple(self.history))
        object.__setattr__(self, "transitions", tuple(self.transitions))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))

    @property
    def current_hash(self) -> str:
        return _hash_payload(self.to_snapshot())

    def get_run(self, run_id: str) -> GraphState:
        try:
            return self.run_states[run_id]
        except KeyError as exc:
            raise KeyError(f"unknown graph run state: {run_id}") from exc

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "run_states": {
                run_id: self.run_states[run_id].to_dict()
                for run_id in sorted(self.run_states)
            },
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_snapshot(),
            "current_hash": self.current_hash,
            "history": tuple(version.to_dict() for version in self.history),
            "transitions": tuple(transition.to_dict() for transition in self.transitions),
            "created_at": str(self.created_at),
            "updated_at": str(self.updated_at),
        }


class StateEngine:
    """Pure state transition engine with append-only version history."""

    def __init__(self, initial_state: GlobalSystemState | None = None) -> None:
        self._state = initial_state or GlobalSystemState(metadata={"system": "ANUBIS"})

    @property
    def current(self) -> GlobalSystemState:
        return self._state

    def register_run(
        self,
        run_state: GraphState,
        *,
        actor: str = "graph.orchestrator",
        reason: str = "Register graph run initial state.",
    ) -> GlobalSystemState:
        if run_state.run_id in self._state.run_states:
            raise ValueError(f"graph run already registered: {run_state.run_id}")
        return self._replace_run(
            run_state,
            actor=actor,
            action="state.run.registered",
            reason=reason,
        )

    def transition_run(
        self,
        run_state: GraphState,
        *,
        actor: str,
        action: str,
        reason: str,
    ) -> GlobalSystemState:
        if run_state.run_id not in self._state.run_states:
            raise KeyError(f"graph run must be registered before transition: {run_state.run_id}")
        return self._replace_run(run_state, actor=actor, action=action, reason=reason)

    def history_for_run(self, run_id: str) -> tuple[StateVersion, ...]:
        return tuple(version for version in self._state.history if version.run_id == run_id)

    def transitions_for_run(self, run_id: str) -> tuple[StateTransition, ...]:
        return tuple(transition for transition in self._state.transitions if transition.run_id == run_id)

    def _replace_run(
        self,
        run_state: GraphState,
        *,
        actor: str,
        action: str,
        reason: str,
    ) -> GlobalSystemState:
        before = self._state
        next_run_states = dict(before.run_states)
        previous_run_state = next_run_states.get(run_state.run_id)
        next_run_states[run_state.run_id] = run_state
        provisional = replace(
            before,
            version=before.version + 1,
            run_states=next_run_states,
            updated_at=utcnow(),
        )
        transition = StateTransition(
            sequence=len(before.transitions) + 1,
            run_id=run_state.run_id,
            actor=actor,
            action=action,
            from_version=before.version,
            to_version=provisional.version,
            reason=reason,
            changed_fields=self._changed_fields(previous_run_state, run_state),
            before_hash=before.current_hash,
            after_hash=provisional.current_hash,
        )
        version = StateVersion(
            version=provisional.version,
            state_hash=provisional.current_hash,
            run_id=run_state.run_id,
            state=run_state,
            transition=transition,
        )
        self._state = replace(
            provisional,
            history=(*before.history, version),
            transitions=(*before.transitions, transition),
            updated_at=utcnow(),
        )
        return self._state

    @staticmethod
    def _changed_fields(previous: GraphState | None, current: GraphState) -> tuple[str, ...]:
        if previous is None:
            return ("run_states",)
        previous_payload = previous.to_dict()
        current_payload = current.to_dict()
        return tuple(
            key
            for key in sorted(current_payload)
            if previous_payload.get(key) != current_payload.get(key)
        )


__all__ = [
    "GlobalSystemState",
    "StateEngine",
    "StateTransition",
    "StateVersion",
]
