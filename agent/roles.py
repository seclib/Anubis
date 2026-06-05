from __future__ import annotations

from agent.base import AgentState

BUILDER = "builder"
RESEARCHER = "researcher"
ANALYST = "analyst"
ORCHESTRATOR = "orchestrator"

CORE_AGENTS: dict[str, AgentState] = {
    BUILDER: "idle",
    RESEARCHER: "idle",
    ANALYST: "idle",
    ORCHESTRATOR: "active",
}

STATE_ORDER = (BUILDER, RESEARCHER, ANALYST, ORCHESTRATOR)

__all__ = [
    "ANALYST",
    "BUILDER",
    "CORE_AGENTS",
    "ORCHESTRATOR",
    "RESEARCHER",
    "STATE_ORDER",
]
