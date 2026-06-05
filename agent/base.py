from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AgentState = Literal["idle", "running", "completed", "active"]

VALID_STATES: frozenset[str] = frozenset({"idle", "running", "completed", "active"})


@dataclass(frozen=True)
class Agent:
    name: str
    state: str


def normalize_agent_name(name: str) -> str:
    return name.strip().lower().replace(" ", "-")


__all__ = ["Agent", "AgentState", "VALID_STATES", "normalize_agent_name"]
