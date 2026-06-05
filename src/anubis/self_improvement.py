from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from uuid import uuid4

from anubis.architecture import (
    ArchitectureAnalyzer,
    ArchitectureFinding,
    PullRequestSystem,
    RefactorPlanner,
    RefactorProposal,
)
from anubis.events import EventBus
from anubis.types import Event, EventType, utcnow


class PerformanceSignal(StrEnum):
    TASK_FAILURE_RATE = "task_failure_rate"
    SANDBOX_DENIAL_RATE = "sandbox_denial_rate"
    KILL_SWITCHES = "kill_switches"
    ARCHITECTURE_FINDINGS = "architecture_findings"


class UpgradeRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class PerformanceFinding:
    signal: PerformanceSignal
    score: float
    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    findings: tuple[PerformanceFinding, ...]
    event_count: int
    generated_at: object = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))


@dataclass(frozen=True, slots=True)
class UpgradeProposal:
    id: str
    title: str
    rationale: str
    risk: UpgradeRisk
    refactor: RefactorProposal | None = None
    performance_findings: tuple[PerformanceFinding, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "performance_findings", tuple(self.performance_findings))


@dataclass(frozen=True, slots=True)
class SimulationResult:
    proposal_id: str
    safe: bool
    expected_score_delta: float
    explanation: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class PatchGenerationResult:
    proposal_id: str
    applied: bool
    simulation: SimulationResult
    changed_files: tuple[str, ...]
    errors: tuple[str, ...] = field(default_factory=tuple)
    patch: str = ""
    requires_human_approval: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed_files", tuple(self.changed_files))
        object.__setattr__(self, "errors", tuple(self.errors))


class PerformanceAnalyzer:
    """Analyzes ANUBIS event history for self-performance signals."""

    def __init__(
        self,
        *,
        failure_rate_threshold: float = 0.25,
        sandbox_denial_threshold: int = 3,
        event_bus: EventBus | None = None,
    ) -> None:
        self.failure_rate_threshold = failure_rate_threshold
        self.sandbox_denial_threshold = sandbox_denial_threshold
        self.event_bus = event_bus

    async def analyze_events(self, events: Sequence[Event]) -> PerformanceReport:
        event_count = len(events)
        task_finished = sum(
            1 for event in events if event.type in {EventType.TASK_SUCCEEDED, EventType.TASK_FAILED}
        )
        task_failed = sum(1 for event in events if event.type == EventType.TASK_FAILED)
        sandbox_denied = sum(1 for event in events if event.type == EventType.SANDBOX_DENIED)
        kill_switches = sum(1 for event in events if event.type == EventType.SAFETY_KILL_SWITCH_TRIGGERED)
        architecture_findings = sum(
            1 for event in events if event.type == EventType.ARCHITECTURE_FINDING_CREATED
        )
        findings: list[PerformanceFinding] = []

        failure_rate = task_failed / task_finished if task_finished else 0.0
        if failure_rate > self.failure_rate_threshold:
            findings.append(
                PerformanceFinding(
                    signal=PerformanceSignal.TASK_FAILURE_RATE,
                    score=failure_rate,
                    message=f"Task failure rate {failure_rate:.3f} exceeds threshold.",
                    metadata={"failed": task_failed, "finished": task_finished},
                )
            )

        if sandbox_denied >= self.sandbox_denial_threshold:
            findings.append(
                PerformanceFinding(
                    signal=PerformanceSignal.SANDBOX_DENIAL_RATE,
                    score=float(sandbox_denied),
                    message="Sandbox denial volume suggests permissions or planning need review.",
                    metadata={"sandbox_denied": sandbox_denied},
                )
            )

        if kill_switches:
            findings.append(
                PerformanceFinding(
                    signal=PerformanceSignal.KILL_SWITCHES,
                    score=float(kill_switches),
                    message="Kill-switch triggers indicate unsafe agent behavior.",
                    metadata={"kill_switches": kill_switches},
                )
            )

        if architecture_findings:
            findings.append(
                PerformanceFinding(
                    signal=PerformanceSignal.ARCHITECTURE_FINDINGS,
                    score=float(architecture_findings),
                    message="Architecture findings are available for upgrade planning.",
                    metadata={"architecture_findings": architecture_findings},
                )
            )

        report = PerformanceReport(findings=tuple(findings), event_count=event_count)
        if self.event_bus is not None:
            await self.event_bus.publish(
                Event(
                    type=EventType.SELF_PERFORMANCE_ANALYZED,
                    producer="self_improvement",
                    payload={
                        "event_count": report.event_count,
                        "findings": len(report.findings),
                    },
                )
            )
        return report


class UpgradePlanner:
    """Combines performance and architecture findings into safe upgrade proposals."""

    def __init__(
        self,
        *,
        architecture_analyzer: ArchitectureAnalyzer | None = None,
        refactor_planner: RefactorPlanner | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.architecture_analyzer = architecture_analyzer or ArchitectureAnalyzer()
        self.refactor_planner = refactor_planner or RefactorPlanner()
        self.event_bus = event_bus

    async def propose_upgrades(
        self,
        *,
        performance_report: PerformanceReport,
        paths: Sequence[str | Path],
    ) -> tuple[UpgradeProposal, ...]:
        architecture_findings = await self.architecture_analyzer.analyze_paths(paths)
        refactors = await self.refactor_planner.propose(architecture_findings)
        proposals: list[UpgradeProposal] = []

        for refactor in refactors:
            proposals.append(
                UpgradeProposal(
                    id=f"upgrade_{uuid4().hex}",
                    title=refactor.title,
                    rationale=refactor.rationale,
                    risk=UpgradeRisk.LOW,
                    refactor=refactor,
                    performance_findings=tuple(
                        finding
                        for finding in performance_report.findings
                        if finding.signal == PerformanceSignal.ARCHITECTURE_FINDINGS
                    ),
                )
            )

        if any(finding.signal == PerformanceSignal.SANDBOX_DENIAL_RATE for finding in performance_report.findings):
            proposals.append(
                UpgradeProposal(
                    id=f"upgrade_{uuid4().hex}",
                    title="Review sandbox permission planning",
                    rationale="Repeated sandbox denials indicate task plans may request unavailable capabilities.",
                    risk=UpgradeRisk.MEDIUM,
                    performance_findings=performance_report.findings,
                )
            )

        result = tuple(proposals)
        if self.event_bus is not None:
            for proposal in result:
                await self.event_bus.publish(
                    Event(
                        type=EventType.SELF_UPGRADE_PROPOSED,
                        producer="self_improvement",
                        payload={
                            "proposal_id": proposal.id,
                            "title": proposal.title,
                            "risk": proposal.risk.value,
                            "has_refactor": proposal.refactor is not None,
                        },
                    )
                )
        return result


class UpgradeSimulator:
    """Estimates impact and safety before self-modification."""

    async def simulate(self, proposal: UpgradeProposal) -> SimulationResult:
        if proposal.risk == UpgradeRisk.HIGH:
            return SimulationResult(
                proposal_id=proposal.id,
                safe=False,
                expected_score_delta=0,
                explanation="High-risk upgrades require external review.",
            )
        if proposal.refactor is None:
            return SimulationResult(
                proposal_id=proposal.id,
                safe=False,
                expected_score_delta=0,
                explanation="Proposal has no concrete refactor to apply safely.",
            )
        if not proposal.refactor.edits:
            return SimulationResult(
                proposal_id=proposal.id,
                safe=False,
                expected_score_delta=0,
                explanation="Refactor proposal contains no edits.",
            )
        return SimulationResult(
            proposal_id=proposal.id,
            safe=True,
            expected_score_delta=float(len(proposal.refactor.findings)),
            explanation="Simulation passed: low-risk base-hash checked refactor.",
            metadata={"edits": len(proposal.refactor.edits)},
        )


class PatchGenerationEngine:
    """Generates safe refactor patches; never modifies source code at runtime."""

    def __init__(
        self,
        *,
        simulator: UpgradeSimulator | None = None,
        pr_system: PullRequestSystem | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.simulator = simulator or UpgradeSimulator()
        self.pr_system = pr_system or PullRequestSystem(event_bus=event_bus)
        self.event_bus = event_bus

    async def apply_safe(self, proposal: UpgradeProposal, *, root: str | Path = ".") -> PatchGenerationResult:
        simulation = await self.simulator.simulate(proposal)
        if self.event_bus is not None:
            await self.event_bus.publish(
                Event(
                    type=EventType.SELF_UPGRADE_SIMULATED,
                    producer="self_improvement",
                    payload={
                        "proposal_id": proposal.id,
                        "safe": simulation.safe,
                        "expected_score_delta": simulation.expected_score_delta,
                    },
                )
            )

        if not simulation.safe or proposal.refactor is None:
            result = PatchGenerationResult(
                proposal_id=proposal.id,
                applied=False,
                simulation=simulation,
                changed_files=(),
                errors=(simulation.explanation,),
                requires_human_approval=True,
            )
        else:
            changes = await self.pr_system.apply(proposal.refactor, root=root)
            result = PatchGenerationResult(
                proposal_id=proposal.id,
                applied=False,
                simulation=simulation,
                changed_files=(),
                errors=changes.errors,
                patch=changes.patch,
                requires_human_approval=True,
            )

        if self.event_bus is not None:
            await self.event_bus.publish(
                Event(
                    type=EventType.PATCH_PROPOSED,
                    producer="self_improvement",
                    payload={
                        "proposal_id": result.proposal_id,
                        "applied": False,
                        "changed_files": result.changed_files,
                        "errors": result.errors,
                        "requires_human_approval": result.requires_human_approval,
                        "patch_bytes": len(result.patch.encode("utf-8")),
                    },
                )
            )
            await self.event_bus.publish(
                Event(
                    type=EventType.PATCH_REQUIRES_APPROVAL,
                    producer="self_improvement",
                    payload={
                        "proposal_id": result.proposal_id,
                        "reason": "Patch proposals are review-only and never applied automatically.",
                    },
                )
            )
        return result
