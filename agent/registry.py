from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from anubis.agents.base import Agent, VALID_STATES, normalize_agent_name
from anubis.agents.roles import CORE_AGENTS, ORCHESTRATOR, STATE_ORDER


class AgentRegistry:
    """Tracks ANUBIS agent state in a shared mutable runtime state object."""

    def __init__(self, state: MutableMapping[str, Any] | None = None) -> None:
        self.state = state if state is not None else {}
        agents = self.state.setdefault("agents", {})
        if not isinstance(agents, MutableMapping):
            self.state["agents"] = {}
        self._ensure_core_agents()

    def spawn(self, name: str) -> str:
        agent_name = self.normalize_name(name)
        if not agent_name:
            return "agent name required"
        if agent_name == ORCHESTRATOR:
            self.update(ORCHESTRATOR, "active")
            return "orchestrator already active"

        existed = agent_name in self._agents
        self._agents[agent_name] = "idle"
        return f"{agent_name} available" if existed else f"{agent_name} spawned"

    def update(self, name: str, state: str) -> None:
        if state not in VALID_STATES:
            raise ValueError(f"invalid agent state: {state}")
        agent_name = self.normalize_name(name)
        if agent_name == ORCHESTRATOR and state == "completed":
            self._agents[agent_name] = "active"
            return
        self._agents[agent_name] = state

    def list(self) -> list[Agent]:
        snapshot = self.snapshot()
        return [Agent(name=name, state=state) for name, state in snapshot.items()]

    def snapshot(self) -> dict[str, str]:
        self._ensure_core_agents()
        ordered: dict[str, str] = {}
        for name in STATE_ORDER:
            if name in self._agents:
                ordered[name] = str(self._agents[name])
        for name in sorted(set(self._agents) - set(ordered)):
            ordered[name] = str(self._agents[name])
        return ordered

    def normalize_name(self, name: str) -> str:
        return normalize_agent_name(name)

    @property
    def _agents(self) -> MutableMapping[str, Any]:
        agents = self.state.setdefault("agents", {})
        if not isinstance(agents, MutableMapping):
            self.state["agents"] = {}
            agents = self.state["agents"]
        return agents

    def _ensure_core_agents(self) -> None:
        for name, state in CORE_AGENTS.items():
            self._agents.setdefault(name, state)


__all__ = ["AgentRegistry"]
