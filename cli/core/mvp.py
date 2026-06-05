from __future__ import annotations

import shlex
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Command:
    name: str
    args: list[str] = field(default_factory=list)
    raw_args: str = ""


@dataclass(frozen=True)
class RenderBlock:
    task: str
    result: str
    status: dict[str, str] | None = None


class CommandParser:
    def parse(self, text: str) -> Command:
        stripped = text.strip()
        if not stripped:
            return Command(name="")
        try:
            parts = shlex.split(stripped)
        except ValueError:
            parts = stripped.split()
        if not parts:
            return Command(name="")
        return Command(name=parts[0].lower(), args=parts[1:], raw_args=stripped[len(parts[0]) :].strip())


BASE_AGENTS = {
    "builder": "idle",
    "researcher": "idle",
    "analyst": "idle",
    "orchestrator": "active",
}


class AgentManager:
    def __init__(self) -> None:
        self._agents = dict(BASE_AGENTS)

    @property
    def states(self) -> dict[str, str]:
        return dict(self._agents)

    def list_agents(self) -> dict[str, str]:
        return self.states

    def spawn(self, name: str) -> str:
        normalized = name.strip().lower().replace(" ", "-")
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


class SwarmEngine:
    def __init__(self, agents: AgentManager) -> None:
        self.agents = agents

    def run(self, goal: str) -> str:
        active_agents = ("orchestrator", "builder", "researcher", "analyst")
        self.agents.activate(*active_agents)
        subtasks = self._subtasks(goal)
        self.agents.complete(*active_agents)
        return "\n".join(
            [
                f"goal: {goal}",
                "subtasks:",
                *(f"- {task}" for task in subtasks),
                "aggregation: completed",
            ]
        )

    def _subtasks(self, goal: str) -> list[str]:
        words = [word.strip(" ,.;:") for word in goal.split() if word.strip(" ,.;:")]
        subject = " ".join(words[:4]) if words else goal
        return [
            f"researcher: gather context for {subject}",
            f"analyst: define constraints for {subject}",
            f"builder: produce execution path for {subject}",
            "orchestrator: merge results",
        ]
