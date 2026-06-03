from __future__ import annotations

from anubis_cli_mvp.agents import AgentManager


class SwarmEngine:
    """Deterministic swarm execution simulator."""

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
