"""Swarm-native coordination engine for production ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.swarm.agent_pool import AgentPool
from core.swarm.consensus import SwarmConsensus, SwarmDecision


@dataclass(frozen=True, slots=True)
class SwarmRunResult:
    objective: str
    agent_outputs: tuple[dict[str, Any], ...]
    decision: SwarmDecision
    explanation: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "agent_outputs": self.agent_outputs,
            "decision": self.decision.to_dict(),
            "explanation": self.explanation,
        }


@dataclass(slots=True)
class SwarmCoordinator:
    """Coordinates planner, analyst, executor, and critic as interchangeable agents."""

    agent_pool: AgentPool = field(default_factory=AgentPool)
    consensus: SwarmConsensus = field(default_factory=SwarmConsensus)

    def run(self, objective: str) -> SwarmRunResult:
        objective = objective.strip()
        if not objective:
            raise ValueError("swarm objective cannot be empty")

        sequence = (
            ("planner", {"objective": objective}),
            ("analyst", {"objective": objective, "observations": [{"summary": objective}]}),
            (
                "executor",
                {
                    "task": {
                        "task_id": "swarm_task",
                        "kind": "swarm.safe_prepare",
                        "objective": objective,
                        "required_capabilities": [],
                    }
                },
            ),
        )
        outputs: list[dict[str, Any]] = []
        for role, payload in sequence:
            agent = self.agent_pool.select(role=role)
            result = agent.run(payload)
            outputs.append({"agent": agent.name, "role": role, "result": result})

        critic = self.agent_pool.select(role="critic")
        critic_result = critic.run({"subject": outputs[-1]["result"]})
        outputs.append({"agent": critic.name, "role": "critic", "result": critic_result})

        votes = tuple(
            self.consensus.vote_from_agent_result(
                agent_name=output["agent"],
                result=output["result"],
                weight=self._weight_for_role(str(output["role"])),
            )
            for output in outputs
        )
        decision = self.consensus.decide(votes)
        return SwarmRunResult(
            objective=objective,
            agent_outputs=tuple(outputs),
            decision=decision,
            explanation=(
                "Swarm executed a deterministic planner -> analyst -> executor -> critic loop.",
                "Agents are selected from AgentPool and can be replaced without changing coordinator logic.",
            ),
        )

    @staticmethod
    def _weight_for_role(role: str) -> float:
        weights = {"planner": 0.9, "analyst": 1.0, "executor": 0.8, "critic": 1.1}
        return weights.get(role, 0.5)


__all__ = ["SwarmCoordinator", "SwarmRunResult"]
