"""Stateless agent contract for ANUBIS production agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

StructuredDict = dict[str, Any]


def _freeze_capabilities(values: frozenset[str] | set[str] | tuple[str, ...]) -> frozenset[str]:
    return frozenset(sorted(value.strip() for value in values if value and value.strip()))


def _copy_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


class AgentInputError(ValueError):
    """Raised when an agent receives malformed structured input."""


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    """Public description used by registries and orchestrators."""

    name: str
    role: str
    capabilities: frozenset[str]
    description: str

    def __post_init__(self) -> None:
        name = self.name.strip()
        role = self.role.strip()
        description = self.description.strip()
        if not name:
            raise ValueError("agent name cannot be empty")
        if not role:
            raise ValueError(f"agent {name} role cannot be empty")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "capabilities", _freeze_capabilities(self.capabilities))
        object.__setattr__(self, "description", description)

    def to_dict(self) -> StructuredDict:
        return {
            "name": self.name,
            "role": self.role,
            "capabilities": sorted(self.capabilities),
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Structured output envelope returned by every agent."""

    ok: bool
    agent: str
    role: str
    output: Mapping[str, Any] = field(default_factory=dict)
    error: Mapping[str, Any] | None = None
    trace: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output", _copy_mapping(self.output))
        if self.error is not None:
            object.__setattr__(self, "error", _copy_mapping(self.error))
        object.__setattr__(self, "trace", tuple(self.trace))

    def to_dict(self) -> StructuredDict:
        payload: StructuredDict = {
            "ok": self.ok,
            "agent": self.agent,
            "role": self.role,
            "output": dict(self.output),
            "trace": list(self.trace),
        }
        if self.error is not None:
            payload["error"] = dict(self.error)
        return payload


@dataclass(frozen=True, slots=True)
class BaseAgent(ABC):
    """Base class for deterministic, stateless ANUBIS workers."""

    descriptor: AgentDescriptor

    @property
    def name(self) -> str:
        return self.descriptor.name

    @property
    def role(self) -> str:
        return self.descriptor.role

    @property
    def capabilities(self) -> frozenset[str]:
        return self.descriptor.capabilities

    def run(self, input_data: Mapping[str, Any]) -> StructuredDict:
        """Process a structured dictionary and always return a dictionary."""

        try:
            if not isinstance(input_data, Mapping):
                raise AgentInputError("agent input must be a structured dictionary")
            normalized_input = dict(input_data)
            output = self.handle(normalized_input)
            if not isinstance(output, Mapping):
                raise TypeError("agent handle() must return a structured dictionary")
            return AgentResult(
                ok=True,
                agent=self.name,
                role=self.role,
                output=dict(output),
                trace=(
                    f"{self.name}.input.validated",
                    f"{self.name}.output.structured",
                ),
            ).to_dict()
        except Exception as exc:
            return AgentResult(
                ok=False,
                agent=self.name,
                role=self.role,
                output={},
                error={
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                    "recoverable": isinstance(exc, AgentInputError),
                },
                trace=(f"{self.name}.error.structured",),
            ).to_dict()

    @abstractmethod
    def handle(self, input_data: StructuredDict) -> StructuredDict:
        """Implement a single agent responsibility."""

    def require_string(self, input_data: Mapping[str, Any], key: str) -> str:
        value = input_data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise AgentInputError(f"missing required string field: {key}")
        return value.strip()

    def optional_mapping(self, input_data: Mapping[str, Any], key: str) -> StructuredDict:
        value = input_data.get(key, {})
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise AgentInputError(f"field {key} must be a dictionary")
        return dict(value)


__all__ = [
    "AgentDescriptor",
    "AgentInputError",
    "AgentResult",
    "BaseAgent",
    "StructuredDict",
]
