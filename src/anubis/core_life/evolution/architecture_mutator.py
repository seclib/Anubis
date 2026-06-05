from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from anubis.architecture import ArchitectureAnalyzer, ArchitectureFinding, RefactorPlanner
from anubis.self_improvement import PerformanceReport, UpgradePlanner, UpgradeProposal


@dataclass(frozen=True, slots=True)
class ArchitectureMutationPlan:
    findings: tuple[ArchitectureFinding, ...]
    proposals: tuple[UpgradeProposal, ...]


class ArchitectureMutator:
    """Detects structural weaknesses and turns them into safe mutation candidates."""

    def __init__(
        self,
        *,
        analyzer: ArchitectureAnalyzer | None = None,
        refactor_planner: RefactorPlanner | None = None,
        upgrade_planner: UpgradePlanner | None = None,
    ) -> None:
        self.analyzer = analyzer or ArchitectureAnalyzer()
        self.refactor_planner = refactor_planner or RefactorPlanner()
        self.upgrade_planner = upgrade_planner or UpgradePlanner(
            architecture_analyzer=self.analyzer,
            refactor_planner=self.refactor_planner,
        )

    async def propose(
        self,
        *,
        performance_report: PerformanceReport,
        paths: Sequence[str | Path],
    ) -> ArchitectureMutationPlan:
        findings = await self.analyzer.analyze_paths(paths)
        proposals = await self.upgrade_planner.propose_upgrades(
            performance_report=performance_report,
            paths=paths,
        )
        return ArchitectureMutationPlan(findings=findings, proposals=proposals)
