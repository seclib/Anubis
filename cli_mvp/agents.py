from __future__ import annotations

from collections.abc import Callable


BASE_AGENTS = {
    "builder": "idle",
    "researcher": "idle",
    "analyst": "idle",
    "orchestrator": "active",
}


class AgentManager:
    """Small state manager for simulated ANUBIS agents."""

    def __init__(self) -> None:
        self._agents = dict(BASE_AGENTS)

    @property
    def states(self) -> dict[str, str]:
        return dict(self._agents)

    def list_agents(self) -> dict[str, str]:
        return self.states

    def spawn(self, name: str) -> str:
        normalized = self._normalize_name(name)
        if not normalized:
            return "agent name required"
        if normalized == "orchestrator":
            self._agents["orchestrator"] = "active"
            return "orchestrator already active"
        if normalized in self._agents:
            self._agents[normalized] = "idle"
            return f"{normalized} available"
        self._agents[normalized] = "idle"
        return f"{normalized} spawned"

    def run(self, agent: str, work: Callable[[], str]) -> str:
        self._set(agent, "running")
        result = work()
        self._set(agent, "completed")
        return result

    def activate(self, *agents: str) -> None:
        for agent in agents:
            self._set(agent, "running")

    def complete(self, *agents: str) -> None:
        for agent in agents:
            self._set(agent, "active" if agent == "orchestrator" else "completed")

    def _set(self, agent: str, state: str) -> None:
        self._agents[agent] = "active" if agent == "orchestrator" and state == "completed" else state

    def _normalize_name(self, name: str) -> str:
        return name.strip().lower().replace(" ", "-")
