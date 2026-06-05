from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

from anubis.core_life.swarm.agent_registry import (
    AgentInsight,
    ResearchAgentRegistry,
    ResearchRole,
    ResearchTask,
)
from anubis.core_life.swarm.consensus_engine import ConsensusEngine, ConsensusOutcome
from anubis.core_life.swarm.role_allocator import RoleAllocation, RoleAllocator
from anubis.core_life.swarm.swarm_memory import SwarmMemory
from anubis.events import EventBus
from anubis.types import Event, EventType


@dataclass(frozen=True, slots=True)
class SwarmResearchResult:
    session_id: str
    stimulus: str
    allocations: tuple[RoleAllocation, ...]
    insights: tuple[AgentInsight, ...]
    consensus: ConsensusOutcome
    reasoning_chain: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reasoning_chain",
            tuple(MappingProxyType(dict(item)) for item in self.reasoning_chain),
        )


class HiveMind:
    """Central controller for collaborative autonomous research."""

    def __init__(
        self,
        *,
        registry: ResearchAgentRegistry,
        memory: SwarmMemory | None = None,
        allocator: RoleAllocator | None = None,
        consensus: ConsensusEngine | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.registry = registry
        self.memory = memory or SwarmMemory()
        self.allocator = allocator or RoleAllocator()
        self.consensus = consensus or ConsensusEngine()
        self.event_bus = event_bus

    async def research(self, stimulus: str) -> SwarmResearchResult:
        session_id = f"swarm_research_{uuid4().hex}"
        await self._publish(
            EventType.SWARM_RESEARCH_STARTED,
            {"session_id": session_id, "stimulus": stimulus},
        )
        allocations = self.allocator.dynamic_switch(self.registry, self.allocator.allocate(self.registry))
        by_role = {allocation.role: allocation for allocation in allocations}
        insights: list[AgentInsight] = []
        trace: list[Mapping[str, Any]] = []

        planner = await self._run_role(ResearchRole.PLANNER, stimulus, session_id, by_role, {})
        insights.append(planner)
        trace.append(self._trace(planner))

        executor = await self._run_role(
            ResearchRole.EXECUTOR,
            stimulus,
            session_id,
            by_role,
            {"planner": planner.summary},
        )
        insights.append(executor)
        trace.append(self._trace(executor))

        analyst_task = self._run_role(
            ResearchRole.ANALYST,
            stimulus,
            session_id,
            by_role,
            {"planner": planner.summary, "executor": executor.summary},
        )
        critic_task = self._run_role(
            ResearchRole.CRITIC,
            stimulus,
            session_id,
            by_role,
            {"planner": planner.summary, "executor": executor.summary},
        )
        analyst, critic = await asyncio.gather(analyst_task, critic_task)
        insights.extend((analyst, critic))
        trace.extend((self._trace(analyst), self._trace(critic)))

        synthesizer = await self._run_role(
            ResearchRole.SYNTHESIZER,
            stimulus,
            session_id,
            by_role,
            {
                "planner": planner.summary,
                "executor": executor.summary,
                "analyst": analyst.summary,
                "critic": critic.summary,
            },
        )
        insights.append(synthesizer)
        trace.append(self._trace(synthesizer))

        scores = {descriptor.name: descriptor.score for descriptor in self.registry.descriptors()}
        consensus = self.consensus.decide(tuple(insights), scores)
        await self._publish(
            EventType.SWARM_CONSENSUS_REACHED,
            {
                "session_id": session_id,
                "decision": consensus.decision,
                "confidence": consensus.confidence,
                "votes": len(consensus.votes),
            },
        )
        await self._publish(
            EventType.SWARM_RESEARCH_COMPLETED,
            {"session_id": session_id, "insights": len(insights), "decision": consensus.decision},
        )
        return SwarmResearchResult(
            session_id=session_id,
            stimulus=stimulus,
            allocations=allocations,
            insights=tuple(insights),
            consensus=consensus,
            reasoning_chain=tuple(trace),
        )

    async def _run_role(
        self,
        role: ResearchRole,
        stimulus: str,
        session_id: str,
        allocations: Mapping[ResearchRole, RoleAllocation],
        context: Mapping[str, Any],
    ) -> AgentInsight:
        allocation = allocations[role]
        agent = self.registry.agent(allocation.agent_name)
        task = ResearchTask(stimulus=stimulus, role=role, session_id=session_id, context=context)
        insight = await agent.handle(task, self.memory)
        self.memory.write_insight(insight, session_id=session_id)
        self.registry.update_score(
            insight.agent_name,
            0.03 if insight.confidence >= 0.7 else -0.04,
        )
        await self._publish(
            EventType.SWARM_AGENT_OUTPUT,
            {
                "session_id": session_id,
                "agent_name": insight.agent_name,
                "role": insight.role.value,
                "confidence": insight.confidence,
                "recommendation": insight.recommendation,
            },
        )
        return insight

    def _trace(self, insight: AgentInsight) -> Mapping[str, Any]:
        return {
            "agent": insight.agent_name,
            "role": insight.role.value,
            "summary": insight.summary,
            "recommendation": insight.recommendation,
            "confidence": insight.confidence,
            "evidence": insight.evidence,
        }

    async def _publish(self, event_type: EventType, payload: Mapping[str, Any]) -> None:
        if self.event_bus is None:
            return
        await self.event_bus.publish(Event(type=event_type, producer="hive_mind", payload=payload))
