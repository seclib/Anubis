"""Auto-patch proposal and validation pipeline for ANUBIS red-team findings."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from inspect import isawaitable
from typing import Any, Protocol
from uuid import uuid4

from anubis.distributed.ci_cd_engine import CICDResult
from anubis.distributed.defense_analyzer import DefenseAnalysisReport
from anubis.distributed.exploit_finder import ExploitAnalysisReport, ExploitPathKind
from anubis.distributed.pr_generator import LinkedWorkItem, PRGenerationRequest, PRGenerationResult


class AutoPatchStage(StrEnum):
    ANALYZED = "analyzed"
    PROPOSED = "proposed"
    PR_SUBMITTED = "pr_submitted"
    CI_VALIDATED = "ci_validated"
    RED_TEAM_VALIDATED = "red_team_validated"
    FAILED = "failed"


class PatchProposalStatus(StrEnum):
    PROPOSED = "proposed"
    SUBMITTED = "submitted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class PatchChangeProposal:
    target: str
    intent: str
    rationale: str
    safety_notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "intent": self.intent,
            "rationale": self.rationale,
            "safety_notes": list(self.safety_notes),
        }


@dataclass(frozen=True)
class FixProposal:
    proposal_id: str
    vulnerability_id: str
    title: str
    probability: float
    severity: str
    status: PatchProposalStatus
    changes: tuple[PatchChangeProposal, ...]
    validation_commands: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_pr_request(self, *, repo_path: str = ".", base_branch: str = "main", create_remote: bool = False) -> PRGenerationRequest:
        return PRGenerationRequest(
            task_id=self.proposal_id,
            goal=self.title,
            repo_path=repo_path,
            base_branch=base_branch,
            head_branch=f"anubis/patch/{self.vulnerability_id}",
            linked_items=(LinkedWorkItem(self.vulnerability_id, "vulnerability"),),
            validation_commands=self.validation_commands,
            labels=("security", "auto-patch"),
            create_remote=create_remote,
            metadata={"fix_proposal": self.to_dict()},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "vulnerability_id": self.vulnerability_id,
            "title": self.title,
            "probability": self.probability,
            "severity": self.severity,
            "status": self.status.value,
            "changes": [change.to_dict() for change in self.changes],
            "validation_commands": list(self.validation_commands),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AutoPatchRequest:
    vulnerability_report: ExploitAnalysisReport | DefenseAnalysisReport
    repo_path: str = "."
    base_branch: str = "main"
    create_remote_pr: bool = False
    validation_commands: tuple[str, ...] = ("pytest",)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutoPatchResult:
    success: bool
    stage: AutoPatchStage
    proposals: tuple[FixProposal, ...]
    pr_results: tuple[Any, ...] = ()
    ci_results: tuple[Any, ...] = ()
    red_team_results: tuple[Any, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "stage": self.stage.value,
            "proposals": [proposal.to_dict() for proposal in self.proposals],
            "pr_results": [_serializable(result) for result in self.pr_results],
            "ci_results": [_serializable(result) for result in self.ci_results],
            "red_team_results": [_serializable(result) for result in self.red_team_results],
            "error": self.error,
        }


class PatchPipeline(Protocol):
    def submit_pr(self, proposal: FixProposal, request: PRGenerationRequest) -> Any: ...

    def run_ci(self, proposal: FixProposal, pr_result: Any) -> Any: ...

    def rerun_red_team(self, proposal: FixProposal, ci_result: Any) -> Any: ...


class FixProposalEngine:
    """Turns vulnerability reports into safe patch proposals without modifying files."""

    def propose(
        self,
        report: ExploitAnalysisReport | DefenseAnalysisReport,
        *,
        validation_commands: tuple[str, ...] = ("pytest",),
    ) -> tuple[FixProposal, ...]:
        if isinstance(report, ExploitAnalysisReport):
            return self._from_exploit_report(report, validation_commands=validation_commands)
        if isinstance(report, DefenseAnalysisReport):
            return self._from_defense_report(report, validation_commands=validation_commands)
        raise TypeError(f"unsupported vulnerability report: {type(report).__name__}")

    def _from_exploit_report(self, report: ExploitAnalysisReport, *, validation_commands: tuple[str, ...]) -> tuple[FixProposal, ...]:
        proposals: list[FixProposal] = []
        for path in report.paths:
            if path.kind == ExploitPathKind.PRIVILEGE_ESCALATION:
                proposals.append(
                    _proposal(
                        path.path_id,
                        "Harden tool permission boundary",
                        path.probability,
                        path.severity,
                        (
                            PatchChangeProposal(
                                target="permission_manager",
                                intent="tighten deny-by-default handling for privileged tool requests",
                                rationale="red-team simulation found a reachable privilege boundary",
                                safety_notes=("route through tool gatekeeper", "keep executor sandbox requirement enforced"),
                            ),
                        ),
                        validation_commands,
                        {"path": path.to_dict()},
                    )
                )
            elif path.kind == ExploitPathKind.UNSAFE_BEHAVIOR_CHAIN:
                proposals.append(
                    _proposal(
                        path.path_id,
                        "Block unsafe agent behavior chain",
                        path.probability,
                        path.severity,
                        (
                            PatchChangeProposal(
                                target="anomaly_engine",
                                intent="raise role-violation confidence and add mitigation coverage for chained findings",
                                rationale="SOC behavior analysis detected multiple unsafe actions from one agent",
                                safety_notes=("preserve read-only planner/reviewer boundaries",),
                            ),
                        ),
                        validation_commands,
                        {"path": path.to_dict()},
                    )
                )
            elif path.kind == ExploitPathKind.CONTAINMENT_BYPASS:
                proposals.append(
                    _proposal(
                        path.path_id,
                        "Close containment bypass",
                        path.probability,
                        path.severity,
                        (
                            PatchChangeProposal(
                                target="sandbox_runtime",
                                intent="add failing regression guard for bypassed containment condition",
                                rationale="red-team execution reported bypass_detected",
                                safety_notes=("do not relax sandbox isolation", "require red-team replay before PR readiness"),
                            ),
                        ),
                        validation_commands,
                        {"path": path.to_dict()},
                    )
                )

        for weak_link in report.weak_links:
            proposals.append(
                _proposal(
                    weak_link.id,
                    f"Reduce weak-link risk in {weak_link.id}",
                    weak_link.risk_score,
                    _severity(weak_link.risk_score),
                    (
                        PatchChangeProposal(
                            target=str(weak_link.metadata.get("id") or weak_link.id),
                            intent="add validation, isolation, or dependency checks around high-risk execution step",
                            rationale="task graph analysis marked this node as a weak link",
                            safety_notes=("patch must be proposed through PR pipeline only",),
                        ),
                    ),
                    validation_commands,
                    {"weak_link": weak_link.to_dict()},
                )
            )
        return tuple(_dedupe(proposals))

    def _from_defense_report(self, report: DefenseAnalysisReport, *, validation_commands: tuple[str, ...]) -> tuple[FixProposal, ...]:
        proposals: list[FixProposal] = []
        for finding in report.findings:
            target = "anomaly_engine"
            title = "Improve red-team detection coverage"
            intent = "add detection rule or telemetry mapping for missed simulated attack"
            if finding.code == "containment_gap":
                target = "sandbox_runtime"
                title = "Strengthen containment enforcement"
                intent = "add containment regression guard and fail-closed handling"
            elif finding.code == "no_blocking_response":
                target = "soc_response_engine"
                title = "Add active SOC blocking response"
                intent = "map detected anomaly to pause, isolate, or kill-switch mitigation"
            proposals.append(
                _proposal(
                    finding.code,
                    title,
                    max(0.3, 1 - report.metrics.detection_rate),
                    finding.severity,
                    (
                        PatchChangeProposal(
                            target=target,
                            intent=intent,
                            rationale=finding.message,
                            safety_notes=("must pass CI/CD before PR creation", "must rerun red-team validation after patch"),
                        ),
                    ),
                    validation_commands,
                    {"finding": finding.to_dict(), "metrics": report.metrics.to_dict()},
                )
            )
        return tuple(_dedupe(proposals))


class AutoPatchGenerator:
    """Coordinates fix proposals through PR, CI/CD, and red-team validation gates."""

    def __init__(self, *, proposal_engine: FixProposalEngine | None = None, pipeline: PatchPipeline | None = None) -> None:
        self.proposal_engine = proposal_engine or FixProposalEngine()
        self.pipeline = pipeline

    async def run(self, request: AutoPatchRequest) -> AutoPatchResult:
        try:
            proposals = self.proposal_engine.propose(request.vulnerability_report, validation_commands=request.validation_commands)
            if not proposals:
                return AutoPatchResult(success=False, stage=AutoPatchStage.FAILED, proposals=(), error="no fix proposals generated")
            if self.pipeline is None:
                return AutoPatchResult(success=True, stage=AutoPatchStage.PROPOSED, proposals=proposals)

            pr_results: list[Any] = []
            ci_results: list[Any] = []
            red_team_results: list[Any] = []
            for proposal in proposals:
                pr_request = proposal.to_pr_request(repo_path=request.repo_path, base_branch=request.base_branch, create_remote=request.create_remote_pr)
                pr_result = await _maybe_await(self.pipeline.submit_pr(proposal, pr_request))
                pr_results.append(pr_result)
                if not _success(pr_result):
                    return AutoPatchResult(False, AutoPatchStage.FAILED, proposals, tuple(pr_results), tuple(ci_results), tuple(red_team_results), "PR generation failed")

                ci_result = await _maybe_await(self.pipeline.run_ci(proposal, pr_result))
                ci_results.append(ci_result)
                if not _success(ci_result):
                    return AutoPatchResult(False, AutoPatchStage.FAILED, proposals, tuple(pr_results), tuple(ci_results), tuple(red_team_results), "CI/CD validation failed")

                red_team_result = await _maybe_await(self.pipeline.rerun_red_team(proposal, ci_result))
                red_team_results.append(red_team_result)
                if not _success(red_team_result):
                    return AutoPatchResult(False, AutoPatchStage.FAILED, proposals, tuple(pr_results), tuple(ci_results), tuple(red_team_results), "red-team validation failed")

            return AutoPatchResult(
                success=True,
                stage=AutoPatchStage.RED_TEAM_VALIDATED,
                proposals=tuple(_mark_submitted(proposals)),
                pr_results=tuple(pr_results),
                ci_results=tuple(ci_results),
                red_team_results=tuple(red_team_results),
            )
        except Exception as exc:
            return AutoPatchResult(False, AutoPatchStage.FAILED, (), error=f"{type(exc).__name__}: {exc}")

    def run_sync(self, request: AutoPatchRequest) -> AutoPatchResult:
        return asyncio.run(self.run(request))


def _proposal(
    vulnerability_id: str,
    title: str,
    probability: float,
    severity: str,
    changes: tuple[PatchChangeProposal, ...],
    validation_commands: tuple[str, ...],
    metadata: dict[str, Any],
) -> FixProposal:
    safe_id = _safe_id(vulnerability_id)
    return FixProposal(
        proposal_id=f"patch_{safe_id}_{uuid4().hex[:8]}",
        vulnerability_id=safe_id,
        title=title,
        probability=round(max(0.0, min(1.0, probability)), 4),
        severity=severity,
        status=PatchProposalStatus.PROPOSED,
        changes=changes,
        validation_commands=validation_commands,
        metadata=metadata,
    )


def _dedupe(proposals: list[FixProposal]) -> list[FixProposal]:
    seen: set[tuple[str, str]] = set()
    unique: list[FixProposal] = []
    for proposal in proposals:
        key = (proposal.vulnerability_id, proposal.title)
        if key in seen:
            continue
        seen.add(key)
        unique.append(proposal)
    return unique


def _mark_submitted(proposals: tuple[FixProposal, ...]) -> tuple[FixProposal, ...]:
    return tuple(
        FixProposal(
            proposal_id=proposal.proposal_id,
            vulnerability_id=proposal.vulnerability_id,
            title=proposal.title,
            probability=proposal.probability,
            severity=proposal.severity,
            status=PatchProposalStatus.SUBMITTED,
            changes=proposal.changes,
            validation_commands=proposal.validation_commands,
            metadata=proposal.metadata,
        )
        for proposal in proposals
    )


async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


def _success(result: Any) -> bool:
    if isinstance(result, (PRGenerationResult, CICDResult)):
        return result.success
    if hasattr(result, "success"):
        return bool(result.success)
    if isinstance(result, dict):
        return bool(result.get("success"))
    return bool(result)


def _serializable(result: Any) -> Any:
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if isinstance(result, dict):
        return dict(result)
    return result


def _severity(probability: float) -> str:
    if probability >= 0.75:
        return "critical"
    if probability >= 0.55:
        return "high"
    if probability >= 0.3:
        return "medium"
    return "low"


def _safe_id(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value)
    return "-".join(part for part in normalized.split("-") if part)[:80] or "vulnerability"


__all__ = [
    "AutoPatchGenerator",
    "AutoPatchRequest",
    "AutoPatchResult",
    "AutoPatchStage",
    "FixProposal",
    "FixProposalEngine",
    "PatchChangeProposal",
    "PatchPipeline",
    "PatchProposalStatus",
]
