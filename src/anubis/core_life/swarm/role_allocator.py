from __future__ import annotations

from dataclasses import dataclass

from anubis.core_life.swarm.agent_registry import ResearchAgentRegistry, ResearchRole


@dataclass(frozen=True, slots=True)
class RoleAllocation:
    role: ResearchRole
    agent_name: str
    score: float
    reason: str


class RoleAllocator:
    def __init__(self, *, minimum_score: float = 0.2) -> None:
        self.minimum_score = minimum_score

    def allocate(self, registry: ResearchAgentRegistry) -> tuple[RoleAllocation, ...]:
        allocations = []
        for role in ResearchRole:
            candidates = registry.agents_for_role(role)
            if not candidates:
                raise LookupError(f"no research agent registered for role: {role}")
            selected = candidates[0]
            score = registry.score(selected.descriptor.name)
            allocations.append(
                RoleAllocation(
                    role=role,
                    agent_name=selected.descriptor.name,
                    score=score,
                    reason=(
                        f"Selected highest-scoring {role.value} agent "
                        f"with score {score:.3f}."
                    ),
                )
            )
        return tuple(allocations)

    def dynamic_switch(
        self,
        registry: ResearchAgentRegistry,
        allocations: tuple[RoleAllocation, ...],
    ) -> tuple[RoleAllocation, ...]:
        switched = []
        for allocation in allocations:
            if allocation.score >= self.minimum_score:
                switched.append(allocation)
                continue
            candidates = registry.agents_for_role(allocation.role)
            replacement = next(
                (
                    agent
                    for agent in candidates
                    if agent.descriptor.name != allocation.agent_name
                    and registry.score(agent.descriptor.name) >= self.minimum_score
                ),
                None,
            )
            if replacement is None:
                switched.append(allocation)
                continue
            switched.append(
                RoleAllocation(
                    role=allocation.role,
                    agent_name=replacement.descriptor.name,
                    score=registry.score(replacement.descriptor.name),
                    reason=f"Switched from underperforming agent {allocation.agent_name}.",
                )
            )
        return tuple(switched)
