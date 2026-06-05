from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from anubis.core_life.evolution.architecture_mutator import (
    ArchitectureMutationPlan,
    ArchitectureMutator,
)
from anubis.core_life.evolution.fitness_function import FitnessFunction, FitnessScore
from anubis.core_life.evolution.version_control_tree import GenomeVersion, VersionControlTree
from anubis.events import EventBus
from anubis.memory import MemoryRecord
from anubis.self_improvement import (
    PatchGenerationEngine,
    PerformanceAnalyzer,
    PerformanceReport,
    SimulationResult,
    UpgradeProposal,
    UpgradeSimulator,
)
from anubis.types import Event, EventType


@dataclass(frozen=True, slots=True)
class EvolutionPolicy:
    enabled: bool = False
    approved_paths: tuple[str, ...] = (
        "src/anubis/agents_life",
        "src/anubis/core_life/evolution",
        "src/anubis/observability",
    )
    forbidden_paths: tuple[str, ...] = (
        "bootstrap.py",
        "src/anubis/bootstrap.py",
        "src/anubis/core_life/living_loop.py",
        "src/anubis/orchestrator.py",
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "approved_paths", tuple(self.approved_paths))
        object.__setattr__(self, "forbidden_paths", tuple(self.forbidden_paths))


@dataclass(frozen=True, slots=True)
class EvolutionCycleResult:
    enabled: bool
    fitness: FitnessScore
    performance_report: PerformanceReport
    mutation_plan: ArchitectureMutationPlan | None
    simulations: tuple[SimulationResult, ...] = field(default_factory=tuple)
    genome_versions: tuple[GenomeVersion, ...] = field(default_factory=tuple)
    rejected: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "simulations", tuple(self.simulations))
        object.__setattr__(self, "genome_versions", tuple(self.genome_versions))
        object.__setattr__(self, "rejected", tuple(self.rejected))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class EvolutionEngine:
    """Optional evolution loop that proposes patches but never applies source changes."""

    def __init__(
        self,
        *,
        policy: EvolutionPolicy | None = None,
        fitness_function: FitnessFunction | None = None,
        performance_analyzer: PerformanceAnalyzer | None = None,
        architecture_mutator: ArchitectureMutator | None = None,
        simulator: UpgradeSimulator | None = None,
        version_tree: VersionControlTree | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.policy = policy or EvolutionPolicy()
        self.fitness_function = fitness_function or FitnessFunction()
        self.performance_analyzer = performance_analyzer or PerformanceAnalyzer(event_bus=event_bus)
        self.architecture_mutator = architecture_mutator or ArchitectureMutator()
        self.simulator = simulator or UpgradeSimulator()
        self.version_tree = version_tree or VersionControlTree()
        self.event_bus = event_bus

    async def evolve(
        self,
        *,
        events: Sequence[Event],
        paths: Sequence[str | Path],
        memory_records: Sequence[MemoryRecord] = (),
        root: str | Path = ".",
    ) -> EvolutionCycleResult:
        fitness = self.fitness_function.evaluate(events, memory_records=memory_records)
        performance = await self.performance_analyzer.analyze_events(events)
        await self._publish(
            EventType.EVOLUTION_ANALYZED,
            {
                "enabled": self.policy.enabled,
                "fitness": fitness.as_dict(),
                "event_count": len(events),
            },
        )

        if not self.policy.enabled:
            return EvolutionCycleResult(
                enabled=False,
                fitness=fitness,
                performance_report=performance,
                mutation_plan=None,
                metadata={"reason": "evolution mode disabled"},
            )

        mutation_plan = await self.architecture_mutator.propose(
            performance_report=performance,
            paths=paths,
        )
        simulations: list[SimulationResult] = []
        versions: list[GenomeVersion] = []
        rejected: list[str] = []

        for proposal in mutation_plan.proposals:
            reason = self._policy_rejection(proposal)
            if reason is not None:
                rejected.append(reason)
                await self._publish(
                    EventType.EVOLUTION_POLICY_REJECTED,
                    {"proposal_id": proposal.id, "reason": reason},
                )
                continue

            simulation = await self.simulator.simulate(proposal)
            simulations.append(simulation)
            versions.append(
                self.version_tree.record_candidate(
                    proposal,
                    simulation,
                    fitness_before=fitness.as_dict(),
                )
            )
            await self._publish_version(versions[-1])

        return EvolutionCycleResult(
            enabled=True,
            fitness=fitness,
            performance_report=performance,
            mutation_plan=mutation_plan,
            simulations=tuple(simulations),
            genome_versions=tuple(versions),
            rejected=tuple(rejected),
        )

    def _policy_rejection(self, proposal: UpgradeProposal) -> str | None:
        if proposal.refactor is None:
            return None
        for edit in proposal.refactor.edits:
            path = edit.path
            if any(path == forbidden or path.startswith(f"{forbidden}/") for forbidden in self.policy.forbidden_paths):
                return f"Proposal {proposal.id} touches forbidden path: {path}."
            if not any(path.startswith(approved) for approved in self.policy.approved_paths):
                return f"Proposal {proposal.id} is outside approved evolution paths: {path}."
        return None

    async def _publish_version(self, version: GenomeVersion) -> None:
        await self._publish(
            EventType.EVOLUTION_VERSION_CREATED,
            {
                "version_id": version.id,
                "parent_id": version.parent_id,
                "proposal_id": version.proposal_id,
                "applied": version.applied,
                "rollback_reference": version.rollback_reference,
            },
        )

    async def _publish(self, event_type: EventType, payload: Mapping[str, Any]) -> None:
        if self.event_bus is None:
            return
        await self.event_bus.publish(
            Event(type=event_type, producer="evolution", payload=payload)
        )


SafeSelfRefactorEngine = EvolutionEngine
