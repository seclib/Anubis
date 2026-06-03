from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any, Literal


AgentState = Literal["idle", "running", "completed", "active"]

CORE_AGENTS: dict[str, AgentState] = {
    "builder": "idle",
    "researcher": "idle",
    "analyst": "idle",
    "orchestrator": "active",
}
STATE_ORDER = ("builder", "researcher", "analyst", "orchestrator")
VALID_STATES = {"idle", "running", "completed", "active"}


@dataclass(frozen=True)
class Agent:
    name: str
    state: str


class AgentRegistry:
    """Extendable registry for ANUBIS CLI agent state."""

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
        if agent_name == "orchestrator":
            self.update("orchestrator", "active")
            return "orchestrator already active"

        existed = agent_name in self._agents
        self._agents[agent_name] = "idle"
        return f"{agent_name} available" if existed else f"{agent_name} spawned"

    def update(self, name: str, state: str) -> None:
        if state not in VALID_STATES:
            raise ValueError(f"invalid agent state: {state}")
        agent_name = self.normalize_name(name)
        if agent_name == "orchestrator" and state == "completed":
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
        return name.strip().lower().replace(" ", "-")

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


__all__ = ["Agent", "AgentRegistry", "AgentState", "CORE_AGENTS", "STATE_ORDER"]
