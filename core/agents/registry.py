"""Deterministic registry for stateless ANUBIS agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.agents.analyst_agent import AnalystAgent
from core.agents.base_agent import AgentInputError, BaseAgent, StructuredDict
from core.agents.critic_agent import CriticAgent
from core.agents.executor_agent import ExecutorAgent
from core.agents.planner_agent import PlannerAgent


@dataclass(slots=True)
class AgentRegistry:
    """In-memory registry for stateless agent instances."""

    agents: dict[str, BaseAgent] = field(default_factory=dict)

    def register(self, agent: BaseAgent) -> None:
        if agent.name in self.agents:
            raise ValueError(f"agent already registered: {agent.name}")
        self.agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent:
        try:
            return self.agents[name]
        except KeyError as exc:
            raise LookupError(f"unknown agent: {name}") from exc

    def descriptors(self) -> list[StructuredDict]:
        return [
            self.agents[name].descriptor.to_dict()
            for name in sorted(self.agents)
        ]

    def select(self, *, role: str | None = None, capability: str | None = None) -> BaseAgent:
        candidates = list(self.agents.values())
        if role is not None:
            candidates = [agent for agent in candidates if agent.role == role]
        if capability is not None:
            candidates = [agent for agent in candidates if capability in agent.capabilities]
        if not candidates:
            raise LookupError("no agent matches requested role/capability")
        return sorted(candidates, key=lambda agent: agent.name)[0]

    def run(self, agent_name: str, input_data: Mapping[str, Any]) -> StructuredDict:
        return self.get(agent_name).run(input_data)


def build_default_agent_registry() -> AgentRegistry:
    registry = AgentRegistry()
    for agent in (PlannerAgent(), AnalystAgent(), ExecutorAgent(), CriticAgent()):
        registry.register(agent)
    return registry


@dataclass(slots=True)
class AgentFramework:
    """Convenience facade for ANUBIS multi-agent workers."""

    registry: AgentRegistry = field(default_factory=build_default_agent_registry)

    def run_by_role(self, role: str, input_data: Mapping[str, Any]) -> StructuredDict:
        if not isinstance(input_data, Mapping):
            raise AgentInputError("agent input must be a structured dictionary")
        agent = self.registry.select(role=role)
        return agent.run(input_data)

    def run_pipeline(self, objective: str, observations: list[Any] | None = None) -> StructuredDict:
        planner_result = self.run_by_role("planner", {"objective": objective})
        analyst_result = self.run_by_role(
            "analyst",
            {"objective": objective, "observations": observations or []},
        )

        task = {}
        if planner_result["ok"]:
            tasks = planner_result["output"]["task_graph"]["tasks"]
            task = tasks[0] if tasks else {}
        executor_result = self.run_by_role("executor", {"task": task})
        critic_result = self.run_by_role("critic", {"subject": executor_result})

        return {
            "ok": all(
                result["ok"]
                for result in (planner_result, analyst_result, executor_result, critic_result)
            ),
            "results": {
                "planner": planner_result,
                "analyst": analyst_result,
                "executor": executor_result,
                "critic": critic_result,
            },
        }


__all__ = ["AgentFramework", "AgentRegistry", "build_default_agent_registry"]
