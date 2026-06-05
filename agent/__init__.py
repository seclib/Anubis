"""Agent orchestration compatibility exports."""
from __future__ import annotations

from agent.base import Agent, AgentState, VALID_STATES, normalize_agent_name
from agent.roles import (
    ANALYST,
    BUILDER,
    CORE_AGENTS,
    ORCHESTRATOR,
    RESEARCHER,
    STATE_ORDER,
)


_LAZY_EXPORTS = {
    "AgentDispatcher": ("agent.swarm", "AgentDispatcher"),
    "AgentExecutor": ("agent.swarm", "AgentExecutor"),
    "AgentRegistry": ("agent.registry", "AgentRegistry"),
    "SwarmAgentResult": ("agent.swarm", "SwarmAgentResult"),
    "SwarmAssignment": ("agent.swarm", "SwarmAssignment"),
    "SwarmEngine": ("agent.swarm", "SwarmEngine"),
    "SwarmResult": ("agent.swarm", "SwarmResult"),
}


def __getattr__(name: str):
    try:
        module_name, attribute = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = __import__(module_name, fromlist=[attribute])
    value = getattr(module, attribute)
    globals()[name] = value
    return value


__all__ = [
    "ANALYST",
    "BUILDER",
    "CORE_AGENTS",
    "ORCHESTRATOR",
    "RESEARCHER",
    "STATE_ORDER",
    "Agent",
    "AgentDispatcher",
    "AgentExecutor",
    "AgentRegistry",
    "AgentState",
    "SwarmAgentResult",
    "SwarmAssignment",
    "SwarmEngine",
    "SwarmResult",
    "VALID_STATES",
    "normalize_agent_name",
]
