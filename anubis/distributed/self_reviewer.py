"""Self-review engine for ANUBIS autonomous code changes."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field, replace
from enum import StrEnum
from inspect import isawaitable
from typing import Any

from anubis.distributed.contracts import EventType, OrchestrationEvent
from anubis.distributed.event_bus import EventBus
from anubis.distributed.feature_engine import FeatureEngineResult
from anubis.distributed.git_agent import GitAutonomyResult
from anubis.distributed.pr_generator import PRGenerationResult, PullRequestPayload
from anubis.distributed.task_graph import TaskGraphNode, TaskGraphNodeType
from anubis.distributed.worker_pool import ExecutorWorkerPool


class SelfReviewRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SelfReviewRecommendation(StrEnum):
    APPROVE = "approve"
    FIX = "fix"
    REJECT = "reject"


class SelfReviewStage(StrEnum):
    STATIC_ANALYSIS = "static_analysis"
    LOGIC_VALIDATION = "logic_validation"
    RISK_SCORING = "risk_scoring"
    FIXING = "fixing"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class StaticFinding:
    source: str
    message: str
    severity: SelfReviewRisk = SelfReviewRisk.MEDIUM
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "message": self.message,
            "severity": self.severity.value,
            "path": self.path,
        }


@dataclass(frozen=True)
class StaticAnalysisReport:
    success: bool
    findings: tuple[StaticFinding, ...] = ()
    checks: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "findings": [finding.to_dict() for finding in self.findings],
            "checks": [dict(check) for check in self.checks],
        }


@dataclass(frozen=True)
class LogicValidationReport:
    valid: bool
    matched_terms: tuple[str, ...]
    missing_terms: tuple[str, ...]
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "matched_terms": list(self.matched_terms),
            "missing_terms": list(self.missing_terms),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class SelfReviewRequest:
    task_id: str
    requirement: str
    repo_path: str = "."
    git_result: GitAutonomyResult | None = None
    feature_result: FeatureEngineResult | None = None
    pr_result: PRGenerationResult | None = None
    pr_payload: PullRequestPayload | None = None
    static_commands: tuple[str, ...] = ()
    fix_commands: tuple[str, ...] = ()
    max_fix_attempts: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "requirement": self.requirement,
            "repo_path": self.repo_path,
            "git_result": self.git_result.to_dict() if self.git_result else None,
            "feature_result": self.feature_result.to_dict() if self.feature_result else None,
            "pr_result": self.pr_result.to_dict() if self.pr_result else None,
            "pr_payload": self.pr_payload.to_dict() if self.pr_payload else None,
            "static_commands": list(self.static_commands),
            "fix_commands": list(self.fix_commands),
            "max_fix_attempts": self.max_fix_attempts,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SelfReviewResult:
    task_id: str
    approved: bool
    recommendation: SelfReviewRecommendation
    risk: SelfReviewRisk
    stage: SelfReviewStage
    static_analysis: StaticAnalysisReport
    logic_validation: LogicValidationReport
    issues: tuple[str, ...] = ()
    fix_attempts: int = 0
    fix_results: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "approved": self.approved,
            "recommendation": self.recommendation.value,
            "risk": self.risk.value,
            "stage": self.stage.value,
            "static_analysis": self.static_analysis.to_dict(),
            "logic_validation": self.logic_validation.to_dict(),
            "issues": list(self.issues),
            "fix_attempts": self.fix_attempts,
            "fix_results": [dict(result) for result in self.fix_results],
        }


@dataclass(frozen=True)
class SelfReviewerConfig:
    default_static_commands: tuple[str, ...] = ("python -m compileall .",)
    reject_on_high_risk: bool = True


class SelfReviewEngine:
    """Reviews autonomous code changes before PR submission."""

    BAD_PATTERNS: tuple[tuple[str, str, SelfReviewRisk], ...] = (
        (r"\beval\s*\(", "unsafe eval usage", SelfReviewRisk.HIGH),
        (r"\bexec\s*\(", "unsafe exec usage", SelfReviewRisk.HIGH),
        (r"except\s+Exception\s*:\s*pass", "silent broad exception handling", SelfReviewRisk.HIGH),
        (r"password\s*=\s*['\"][^'\"]+['\"]", "hardcoded password-like value", SelfReviewRisk.HIGH),
        (r"api[_-]?key\s*=\s*['\"][^'\"]+['\"]", "hardcoded api key-like value", SelfReviewRisk.HIGH),
        (r"\bTODO\b|\bFIXME\b", "unfinished marker left in changed code", SelfReviewRisk.MEDIUM),
        (r"\bprint\s*\(", "debug print left in changed code", SelfReviewRisk.LOW),
    )

    STOP_WORDS = frozenset(
        {
            "a",
            "an",
            "and",
            "as",
            "for",
            "in",
            "of",
            "on",
            "or",
            "the",
            "to",
            "with",
            "add",
            "build",
            "create",
            "fix",
            "implement",
            "update",
        }
    )

    def __init__(
        self,
        *,
        executor_pool: ExecutorWorkerPool | None = None,
        event_bus: EventBus | None = None,
        config: SelfReviewerConfig | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.executor_pool = executor_pool or ExecutorWorkerPool(max_workers=1, event_bus=self.event_bus)
        self.config = config or SelfReviewerConfig()

    async def run(self, request: SelfReviewRequest) -> SelfReviewResult:
        self._validate_request(request)
        current = request
        fix_results: list[dict[str, Any]] = []

        for attempt in range(0, max(0, request.max_fix_attempts) + 1):
            await self._publish(current.task_id, SelfReviewStage.STATIC_ANALYSIS, "Running self-review static analysis")
            static_report = await self.static_analysis(current)
            await self._publish(current.task_id, SelfReviewStage.LOGIC_VALIDATION, "Validating feature logic against requirement")
            logic_report = self.logic_validation(current)
            risk = self.score_risk(current, static_report, logic_report)
            issues = self._issues(static_report, logic_report, risk)
            recommendation = self._recommendation(static_report, logic_report, risk, current)

            if recommendation == SelfReviewRecommendation.APPROVE:
                await self._publish(current.task_id, SelfReviewStage.APPROVED, "Self-review approved code")
                return SelfReviewResult(
                    task_id=current.task_id,
                    approved=True,
                    recommendation=recommendation,
                    risk=risk,
                    stage=SelfReviewStage.APPROVED,
                    static_analysis=static_report,
                    logic_validation=logic_report,
                    issues=issues,
                    fix_attempts=attempt,
                    fix_results=tuple(fix_results),
                )

            if recommendation == SelfReviewRecommendation.FIX and attempt < current.max_fix_attempts:
                await self._publish(current.task_id, SelfReviewStage.FIXING, "Self-review requested autonomous fix loop")
                fix_results.extend(await self._run_fix_commands(current, attempt + 1))
                continue

            await self._publish(current.task_id, SelfReviewStage.REJECTED, "Self-review rejected code", {"issues": list(issues)})
            return SelfReviewResult(
                task_id=current.task_id,
                approved=False,
                recommendation=SelfReviewRecommendation.REJECT,
                risk=risk,
                stage=SelfReviewStage.REJECTED,
                static_analysis=static_report,
                logic_validation=logic_report,
                issues=issues,
                fix_attempts=attempt,
                fix_results=tuple(fix_results),
            )

        raise RuntimeError("self-review loop exited unexpectedly")

    def run_sync(self, request: SelfReviewRequest) -> SelfReviewResult:
        return asyncio.run(self.run(request))

    async def static_analysis(self, request: SelfReviewRequest) -> StaticAnalysisReport:
        checks: list[dict[str, Any]] = []
        commands = request.static_commands or self.config.default_static_commands
        for index, command in enumerate(commands, start=1):
            result = await self._run_command(request, f"static:{index:03d}", command)
            checks.append(result)

        findings = list(self._pattern_findings(request))
        for check in checks:
            if not check["success"]:
                findings.append(
                    StaticFinding(
                        source="static_command",
                        message=f"static analysis command failed: {check['command']}",
                        severity=SelfReviewRisk.HIGH,
                    )
                )

        return StaticAnalysisReport(
            success=not findings,
            findings=tuple(findings),
            checks=tuple(checks),
        )

    def logic_validation(self, request: SelfReviewRequest) -> LogicValidationReport:
        required_terms = self._requirement_terms(request.requirement)
        evidence = self._evidence_texts(request)
        evidence_blob = " ".join(evidence).lower()
        matched = tuple(term for term in required_terms if term in evidence_blob)
        missing = tuple(term for term in required_terms if term not in set(matched))
        if not required_terms:
            valid = bool(evidence)
        else:
            # Allow partial match for natural-language requirements while still catching obvious drift.
            valid = len(matched) >= max(1, (len(required_terms) + 1) // 2)
        return LogicValidationReport(
            valid=valid,
            matched_terms=matched,
            missing_terms=missing,
            evidence=tuple(evidence),
        )

    def score_risk(
        self,
        request: SelfReviewRequest,
        static_report: StaticAnalysisReport,
        logic_report: LogicValidationReport,
    ) -> SelfReviewRisk:
        score = 0
        for finding in static_report.findings:
            score += {SelfReviewRisk.LOW: 1, SelfReviewRisk.MEDIUM: 2, SelfReviewRisk.HIGH: 4}[finding.severity]
        if not logic_report.valid:
            score += 3
        if request.git_result and request.git_result.diff:
            diff = request.git_result.diff
            if diff.risk == "high":
                score += 4
            elif diff.risk == "medium":
                score += 2
            if len(diff.changed_files) > 8 or diff.additions + diff.deletions > 300:
                score += 2
        if score >= 4:
            return SelfReviewRisk.HIGH
        if score >= 2:
            return SelfReviewRisk.MEDIUM
        return SelfReviewRisk.LOW

    async def _run_fix_commands(self, request: SelfReviewRequest, attempt: int) -> tuple[dict[str, Any], ...]:
        results: list[dict[str, Any]] = []
        for index, command in enumerate(request.fix_commands, start=1):
            results.append(await self._run_command(request, f"fix:{attempt}:{index:03d}", command))
        return tuple(results)

    async def _run_command(self, request: SelfReviewRequest, node_id: str, command: str) -> dict[str, Any]:
        node = TaskGraphNode(
            id=f"{request.task_id}:self_review:{node_id}",
            type=TaskGraphNodeType.EXECUTE,
            payload={
                "task_id": request.task_id,
                "tool": "run_command",
                "input": {"cmd": command, "cwd": request.repo_path},
                "lock_key": f"cwd:{request.repo_path}",
            },
        )
        result = await self.executor_pool.node_runner(node)
        return {
            "node_id": node_id,
            "command": command,
            "success": result.success,
            "output": result.output,
            "error": result.error,
        }

    def _pattern_findings(self, request: SelfReviewRequest) -> tuple[StaticFinding, ...]:
        diff = request.git_result.diff.raw if request.git_result and request.git_result.diff else ""
        findings: list[StaticFinding] = []
        for pattern, message, severity in self.BAD_PATTERNS:
            for match in re.finditer(pattern, diff, flags=re.IGNORECASE | re.MULTILINE):
                findings.append(
                    StaticFinding(
                        source="diff_pattern",
                        message=message,
                        severity=severity,
                        path=self._nearest_path(diff, match.start()),
                    )
                )
        return tuple(findings)

    def _nearest_path(self, diff: str, position: int) -> str | None:
        preceding = diff[:position].splitlines()
        for line in reversed(preceding):
            if line.startswith("diff --git "):
                parts = line.split()
                if len(parts) >= 4:
                    return parts[3].removeprefix("b/")
        return None

    def _recommendation(
        self,
        static_report: StaticAnalysisReport,
        logic_report: LogicValidationReport,
        risk: SelfReviewRisk,
        request: SelfReviewRequest,
    ) -> SelfReviewRecommendation:
        if static_report.success and logic_report.valid and risk == SelfReviewRisk.LOW:
            return SelfReviewRecommendation.APPROVE
        if risk == SelfReviewRisk.HIGH and self.config.reject_on_high_risk:
            return SelfReviewRecommendation.REJECT
        if request.fix_commands:
            return SelfReviewRecommendation.FIX
        return SelfReviewRecommendation.REJECT

    def _issues(
        self,
        static_report: StaticAnalysisReport,
        logic_report: LogicValidationReport,
        risk: SelfReviewRisk,
    ) -> tuple[str, ...]:
        issues = [finding.message for finding in static_report.findings]
        if not logic_report.valid:
            issues.append(f"requirement coverage insufficient; missing terms: {', '.join(logic_report.missing_terms)}")
        if risk == SelfReviewRisk.HIGH:
            issues.append("high risk change requires rejection or deeper remediation")
        return tuple(dict.fromkeys(issues))

    def _requirement_terms(self, requirement: str) -> tuple[str, ...]:
        terms = [
            term
            for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", requirement.lower())
            if term not in self.STOP_WORDS
        ]
        return tuple(dict.fromkeys(terms[:12]))

    def _evidence_texts(self, request: SelfReviewRequest) -> tuple[str, ...]:
        evidence: list[str] = []
        if request.git_result:
            evidence.extend(commit.message for commit in request.git_result.commits)
            if request.git_result.diff:
                evidence.extend(request.git_result.diff.changed_files)
                evidence.append(request.git_result.diff.summary)
        if request.feature_result:
            evidence.append(request.feature_result.error or "")
            for route in request.feature_result.route_results:
                evidence.append(route.repo_id)
                if route.plan:
                    evidence.extend(step.action for step in route.plan.steps)
        payload = request.pr_payload or (request.pr_result.payload if request.pr_result else None)
        if payload:
            evidence.append(payload.title)
            evidence.append(payload.body)
        return tuple(text for text in evidence if text)

    def _validate_request(self, request: SelfReviewRequest) -> None:
        if not request.task_id.strip():
            raise ValueError("task_id is required")
        if not request.requirement.strip():
            raise ValueError("requirement is required")
        if not request.repo_path.strip():
            raise ValueError("repo_path is required")

    async def _publish(
        self,
        task_id: str,
        stage: SelfReviewStage,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = OrchestrationEvent(
            event_type=EventType.TASK_FAILED if stage == SelfReviewStage.REJECTED else EventType.TASK_STATE_CHANGED,
            task_id=task_id,
            message=message,
            payload={"stage": stage.value, **(payload or {})},
        )
        published = self.event_bus.publish(event)
        if isawaitable(published):
            await published


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


__all__ = [
    "LogicValidationReport",
    "SelfReviewEngine",
    "SelfReviewRecommendation",
    "SelfReviewRequest",
    "SelfReviewResult",
    "SelfReviewRisk",
    "SelfReviewStage",
    "SelfReviewerConfig",
    "StaticAnalysisReport",
    "StaticFinding",
]
