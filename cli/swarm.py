from __future__ import annotations

from dataclasses import dataclass

from cli.agents import AgentRegistry


@dataclass(frozen=True)
class SwarmAssignment:
    agent: str
    task: str


@dataclass(frozen=True)
class SwarmResult:
    goal: str
    assignments: list[SwarmAssignment]
    aggregate: str

    def render(self) -> str:
        lines = [
            f"goal: {self.goal}",
            "assignments:",
            *(f"- {item.agent} -> {item.task}" for item in self.assignments),
            f"aggregate: {self.aggregate}",
        ]
        return "\n".join(lines)


class SwarmEngine:
    """Deterministic swarm execution simulator for ANUBIS CLI."""

    def __init__(self, agents: AgentRegistry) -> None:
        self.agents = agents

    def run(self, goal: str) -> SwarmResult:
        clean_goal = " ".join(goal.split())
        assignments = self.plan(clean_goal)

        for assignment in assignments:
            self.agents.update(assignment.agent, "running")
        self.agents.update("orchestrator", "active")

        for assignment in assignments:
            self.agents.update(assignment.agent, "completed")
        self.agents.update("orchestrator", "active")

        return SwarmResult(
            goal=clean_goal,
            assignments=assignments,
            aggregate="combined swarm result prepared",
        )

    def plan(self, goal: str) -> list[SwarmAssignment]:
        profile = self._profile(goal)
        return [
            SwarmAssignment("builder", profile["builder"]),
            SwarmAssignment("researcher", profile["researcher"]),
            SwarmAssignment("analyst", profile["analyst"]),
        ]

    def _profile(self, goal: str) -> dict[str, str]:
        lowered = goal.lower()
        subject = self._subject(goal)

        if any(word in lowered for word in ("landing", "page", "ui", "interface", "frontend")):
            return {
                "builder": "UI structure",
                "researcher": "design inspiration",
                "analyst": "optimization",
            }

        if any(word in lowered for word in ("api", "backend", "service", "server")):
            return {
                "builder": f"service structure for {subject}",
                "researcher": f"integration context for {subject}",
                "analyst": f"reliability constraints for {subject}",
            }

        if any(word in lowered for word in ("debug", "fix", "error", "failure", "bug")):
            return {
                "builder": f"patch path for {subject}",
                "researcher": f"failure context for {subject}",
                "analyst": f"root cause analysis for {subject}",
            }

        return {
            "builder": f"execution path for {subject}",
            "researcher": f"context discovery for {subject}",
            "analyst": f"risk and constraint review for {subject}",
        }

    def _subject(self, goal: str) -> str:
        words = [word.strip(" ,.;:") for word in goal.split() if word.strip(" ,.;:")]
        return " ".join(words[:5]) if words else goal


__all__ = ["SwarmAssignment", "SwarmEngine", "SwarmResult"]
