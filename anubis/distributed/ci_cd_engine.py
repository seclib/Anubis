"""Fully automated CI/CD gate for ANUBIS autonomous pull requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from inspect import isawaitable
from typing import Any

from anubis.distributed.contracts import EventType, OrchestrationEvent
from anubis.distributed.event_bus import EventBus
from anubis.distributed.git_agent import GitAutonomyResult, GitStage
from anubis.distributed.pr_generator import PRGenerationResult, PRStage
from anubis.distributed.self_reviewer import (
    SelfReviewRecommendation,
    SelfReviewResult,
    SelfReviewRisk,
)
from anubis.distributed.task_graph import TaskGraphNode, TaskGraphNodeType
from anubis.distributed.worker_pool import ExecutorWorkerPool


class CICDStage(StrEnum):
    PR_DETECTED = "pr_detected"
    TESTING = "testing"
    STATIC_ANALYSIS = "static_analysis"
    REVIEW_VALIDATION = "review_validation"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"


class CICDDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True)
class PullRequestSignal:
    pipeline_id: str
    repo_path: str
    pr_number: int | None = None
    title: str = ""
    head_branch: str = ""
    base_branch: str = "main"
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "repo_path": self.repo_path,
            "pr_number": self.pr_number,
            "title": self.title,
            "head_branch": self.head_branch,
            "base_branch": self.base_branch,
            "url": self.url,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CICDCommandResult:
    name: str
    stage: CICDStage
    command: str
    success: bool
    output: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "stage": self.stage.value,
            "command": self.command,
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


@dataclass(frozen=True)
class ReviewerGateResult:
    valid: bool
    issues: tuple[str, ...] = ()
    risk: SelfReviewRisk | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": list(self.issues),
            "risk": self.risk.value if self.risk else None,
        }


@dataclass(frozen=True)
class DeploymentResult:
    success: bool
    checks: tuple[CICDCommandResult, ...] = ()
    environment: str = "production"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "checks": [check.to_dict() for check in self.checks],
            "environment": self.environment,
            "error": self.error,
        }


@dataclass(frozen=True)
class CICDRequest:
    pipeline_id: str
    repo_path: str
    pr_signal: PullRequestSignal | None = None
    pr_result: PRGenerationResult | None = None
    self_review_result: SelfReviewResult | None = None
    git_result: GitAutonomyResult | None = None
    test_commands: tuple[str, ...] = ()
    static_commands: tuple[str, ...] = ()
    deploy_commands: tuple[str, ...] = ()
    deployment_environment: str = "production"
    allow_network: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "repo_path": self.repo_path,
            "pr_signal": self.pr_signal.to_dict() if self.pr_signal else None,
            "pr_result": self.pr_result.to_dict() if self.pr_result else None,
            "self_review_result": self.self_review_result.to_dict() if self.self_review_result else None,
            "git_result": self.git_result.to_dict() if self.git_result else None,
            "test_commands": list(self.test_commands),
            "static_commands": list(self.static_commands),
            "deploy_commands": list(self.deploy_commands),
            "deployment_environment": self.deployment_environment,
            "allow_network": self.allow_network,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CICDResult:
    pipeline_id: str
    success: bool
    stage: CICDStage
    decision: CICDDecision
    checks: tuple[CICDCommandResult, ...] = ()
    reviewer_gate: ReviewerGateResult | None = None
    deployment: DeploymentResult | None = None
    issues: tuple[str, ...] = ()
    error: str | None = None

    @property
    def approved(self) -> bool:
        return self.decision == CICDDecision.APPROVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "success": self.success,
            "stage": self.stage.value,
            "decision": self.decision.value,
            "approved": self.approved,
            "checks": [check.to_dict() for check in self.checks],
            "reviewer_gate": self.reviewer_gate.to_dict() if self.reviewer_gate else None,
            "deployment": self.deployment.to_dict() if self.deployment else None,
            "issues": list(self.issues),
            "error": self.error,
        }


@dataclass(frozen=True)
class CICDEngineConfig:
    default_test_commands: tuple[str, ...] = ("python -m unittest discover tests",)
    default_static_commands: tuple[str, ...] = ("python -m compileall .",)
    default_deploy_commands: tuple[str, ...] = ()
    require_pr_result: bool = True
    require_self_review: bool = True
    require_pushed_git: bool = False
    allow_medium_risk: bool = True
    allow_high_risk: bool = False


class CICDEngine:
    """Coordinates automated PR validation and deployment gates.

    The engine is intentionally orchestration-only. All shell work is delegated
    as ``run_command`` execution nodes to the distributed executor pool.
    """

    def __init__(
        self,
        *,
        executor_pool: ExecutorWorkerPool | None = None,
        event_bus: EventBus | None = None,
        config: CICDEngineConfig | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.executor_pool = executor_pool or ExecutorWorkerPool(max_workers=2, event_bus=self.event_bus)
        self.config = config or CICDEngineConfig()

    async def run(self, request: CICDRequest) -> CICDResult:
        try:
            self._validate_request(request)
            await self._publish(request.pipeline_id, CICDStage.PR_DETECTED, "CI/CD detected pull request")

            tests = await self._run_gate_commands(
                request,
                CICDStage.TESTING,
                request.test_commands or self.config.default_test_commands,
                "test",
            )
            if not self._all_success(tests):
                return await self._reject(request, CICDStage.REJECTED, "test gate failed", checks=tests)

            static = await self._run_gate_commands(
                request,
                CICDStage.STATIC_ANALYSIS,
                request.static_commands or self.config.default_static_commands,
                "static",
            )
            checks = (*tests, *static)
            if not self._all_success(static):
                return await self._reject(request, CICDStage.REJECTED, "static analysis gate failed", checks=checks)

            await self._publish(request.pipeline_id, CICDStage.REVIEW_VALIDATION, "Validating reviewer output")
            reviewer_gate = self.validate_reviewer_output(request)
            if not reviewer_gate.valid:
                return await self._reject(
                    request,
                    CICDStage.REJECTED,
                    "reviewer gate failed",
                    checks=checks,
                    reviewer_gate=reviewer_gate,
                    issues=reviewer_gate.issues,
                )

            await self._publish(request.pipeline_id, CICDStage.APPROVED, "CI/CD approved pull request")
            deployment = await self.deploy(request)
            final_stage = CICDStage.DEPLOYED if deployment.success else CICDStage.FAILED
            result = CICDResult(
                pipeline_id=request.pipeline_id,
                success=deployment.success,
                stage=final_stage,
                decision=CICDDecision.APPROVE,
                checks=checks,
                reviewer_gate=reviewer_gate,
                deployment=deployment,
                error=deployment.error,
            )
            await self._publish(
                request.pipeline_id,
                final_stage,
                "Deployment completed" if deployment.success else "Deployment failed",
                result.to_dict(),
            )
            return result
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            result = CICDResult(
                pipeline_id=request.pipeline_id,
                success=False,
                stage=CICDStage.FAILED,
                decision=CICDDecision.REJECT,
                issues=(error,),
                error=error,
            )
            await self._publish(request.pipeline_id, CICDStage.FAILED, error, result.to_dict())
            return result

    def run_sync(self, request: CICDRequest) -> CICDResult:
        return asyncio.run(self.run(request))

    def validate_reviewer_output(self, request: CICDRequest) -> ReviewerGateResult:
        issues: list[str] = []

        if self.config.require_pr_result:
            if request.pr_result is None:
                issues.append("missing pull request generation result")
            elif not request.pr_result.success or request.pr_result.stage not in {PRStage.READY, PRStage.CREATED}:
                issues.append("pull request result is not ready for CI/CD")

        if self.config.require_pushed_git:
            if request.git_result is None:
                issues.append("missing pushed git result")
            elif not request.git_result.success or request.git_result.stage != GitStage.PUSHED:
                issues.append("git result was not pushed before CI/CD")

        review = request.self_review_result
        if self.config.require_self_review and review is None:
            issues.append("missing self-review result")
            return ReviewerGateResult(valid=False, issues=tuple(issues))
        if review is None:
            return ReviewerGateResult(valid=not issues, issues=tuple(issues))

        if not review.approved or review.recommendation != SelfReviewRecommendation.APPROVE:
            issues.append("self-review did not approve the change")
        if not review.static_analysis.success:
            issues.append("self-review static analysis failed")
        if not review.logic_validation.valid:
            issues.append("self-review logic validation failed")
        if review.risk == SelfReviewRisk.HIGH and not self.config.allow_high_risk:
            issues.append("high-risk code is blocked from automated deployment")
        if review.risk == SelfReviewRisk.MEDIUM and not self.config.allow_medium_risk:
            issues.append("medium-risk code is blocked by CI/CD policy")
        issues.extend(review.issues)

        return ReviewerGateResult(valid=not issues, issues=tuple(issues), risk=review.risk)

    async def deploy(self, request: CICDRequest) -> DeploymentResult:
        commands = request.deploy_commands or self.config.default_deploy_commands
        if not commands:
            return DeploymentResult(
                success=False,
                environment=request.deployment_environment,
                error="no deployment commands configured",
            )

        await self._publish(request.pipeline_id, CICDStage.DEPLOYING, "Triggering deployment")
        checks = await self._run_gate_commands(request, CICDStage.DEPLOYING, commands, "deploy")
        success = self._all_success(checks)
        return DeploymentResult(
            success=success,
            checks=checks,
            environment=request.deployment_environment,
            error=None if success else "deployment gate failed",
        )

    async def _run_gate_commands(
        self,
        request: CICDRequest,
        stage: CICDStage,
        commands: tuple[str, ...],
        prefix: str,
    ) -> tuple[CICDCommandResult, ...]:
        await self._publish(request.pipeline_id, stage, f"Running {stage.value} commands")
        checks: list[CICDCommandResult] = []
        for index, command in enumerate(commands, start=1):
            node = TaskGraphNode(
                id=f"{request.pipeline_id}:{prefix}:{index:03d}",
                type=TaskGraphNodeType.EXECUTE,
                payload={
                    "task_id": request.pipeline_id,
                    "tool": "run_command",
                    "input": {
                        "cmd": command,
                        "cwd": request.repo_path,
                        "allow_network": request.allow_network,
                    },
                    "lock_key": f"cwd:{request.repo_path}",
                },
            )
            result = await self.executor_pool.node_runner(node)
            check = CICDCommandResult(
                name=f"{prefix}:{index:03d}",
                stage=stage,
                command=command,
                success=result.success,
                output=result.output,
                error=result.error,
            )
            checks.append(check)
            if not check.success:
                break
        return tuple(checks)

    def _validate_request(self, request: CICDRequest) -> None:
        if not request.pipeline_id.strip():
            raise ValueError("pipeline_id is required")
        if not request.repo_path.strip():
            raise ValueError("repo_path is required")
        if request.pr_signal is not None and request.pr_signal.pipeline_id != request.pipeline_id:
            raise ValueError("pr_signal pipeline_id must match request pipeline_id")

    def _all_success(self, checks: tuple[CICDCommandResult, ...]) -> bool:
        return bool(checks) and all(check.success for check in checks)

    async def _reject(
        self,
        request: CICDRequest,
        stage: CICDStage,
        error: str,
        *,
        checks: tuple[CICDCommandResult, ...] = (),
        reviewer_gate: ReviewerGateResult | None = None,
        issues: tuple[str, ...] = (),
    ) -> CICDResult:
        result = CICDResult(
            pipeline_id=request.pipeline_id,
            success=False,
            stage=stage,
            decision=CICDDecision.REJECT,
            checks=checks,
            reviewer_gate=reviewer_gate,
            issues=issues or (error,),
            error=error,
        )
        await self._publish(request.pipeline_id, stage, error, result.to_dict())
        return result

    async def _publish(
        self,
        pipeline_id: str,
        stage: CICDStage,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event_type = self._event_type(stage)
        published = self.event_bus.publish(
            OrchestrationEvent(
                event_type=event_type,
                task_id=pipeline_id,
                message=message,
                payload={"stage": stage.value, **(payload or {})},
            )
        )
        if isawaitable(published):
            await published

    def _event_type(self, stage: CICDStage) -> EventType:
        if stage == CICDStage.PR_DETECTED:
            return EventType.TASK_CREATED
        if stage == CICDStage.REJECTED:
            return EventType.TASK_FAILED
        if stage == CICDStage.DEPLOYED:
            return EventType.TASK_COMPLETED
        if stage == CICDStage.FAILED:
            return EventType.TASK_FAILED
        return EventType.TASK_STATE_CHANGED


__all__ = [
    "CICDCommandResult",
    "CICDDecision",
    "CICDEngine",
    "CICDEngineConfig",
    "CICDRequest",
    "CICDResult",
    "CICDStage",
    "DeploymentResult",
    "PullRequestSignal",
    "ReviewerGateResult",
]
