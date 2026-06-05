"""Agent activity dashboard schema."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AgentActivityRow:
    agent_name: str
    status: str
    active_tasks: int
    risk_score: float = 0.0
    last_event: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class AgentActivityDashboard:
    rows: tuple[AgentActivityRow, ...]
    generated_by: str = "anubis"

