"""Autonomous rollback coordinator for unsafe ANUBIS deployments."""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass, field
from enum import StrEnum
from inspect import isawaitable
from typing import Any

from anubis.distributed.ci_cd_engine import CICDResult, CICDStage
from anubis.distributed.contracts import EventType, OrchestrationEvent
from anubis.distributed.event_bus import EventBus
from anubis.distributed.rollback import RollbackSignal
from anubis.distributed.self_reviewer import SelfReviewRecommendation, SelfReviewResult
from anubis.distributed.task_graph import TaskGraphNode, TaskGraphNodeType
from anubis.distributed.worker_pool import ExecutorWorkerPool


class RollbackReason(StrEnum):
    TEST_FAILURE = "test_failure"
    RUNTIME_FAILURE = "runtime_failure"
    REVIEWER_REJECTION = "reviewer_rejection"
    DEPLOYMENT_FAILURE = "deployment_failure"


class RollbackStage(StrEnum):
    DETECTED = "detected"
    REVERTING = "reverting"
    RESTORING = "restoring"
    NOTIFYING = "notifying"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RollbackStrategy(StrEnum):
    REVERT_COMMITS = "revert_commits"
    RESTORE_STABLE_REF = "restore_stable_ref"
    SIGNAL_ONLY = "signal_only"


@dataclass(frozen=True)
class RuntimeFailureSignal:
    name: str
    success: bool
    output: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


@dataclass(frozen=True)
class RollbackDecision:
    required: bool
    reasons: tuple[RollbackReason, ...] = ()
    strategy: RollbackStrategy = RollbackStrategy.SIGNAL_ONLY
    evidence: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "reasons": [reason.value for reason in self.reasons],
            "strategy": self.strategy.value,
            "evidence": [dict(item) for item in self.evidence],
        }


@dataclass(frozen=True)
class RollbackActionResult:
    name: str
    stage: RollbackStage
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
class RollbackNotification:
    sent: bool
    task_id: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sent": self.sent,
            "task_id": self.task_id,
            "message": self.message,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class RollbackRequest:
    rollback_id: str
    task_id: str
    repo_path: str
    ci_cd_result: CICDResult | None = None
    self_review_result: SelfReviewResult | None = None
    rollback_signals: tuple[RollbackSignal, ...] = ()
    runtime_failures: tuple[RuntimeFailureSignal, ...] = ()
    commits_to_revert: tuple[str, ...] = ()
    stable_ref: str | None = "HEAD~1"
    restore_paths: tuple[str, ...] = ()
    push: bool = False
    remote: str = "origin"
    branch: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollback_id": self.rollback_id,
            "task_id": self.task_id,
            "repo_path": self.repo_path,
            "ci_cd_result": self.ci_cd_result.to_dict() if self.ci_cd_result else None,
            "self_review_result": self.self_review_result.to_dict() if self.self_review_result else None,
            "rollback_signals": [signal.to_dict() for signal in self.rollback_signals],
            "runtime_failures": [failure.to_dict() for failure in self.runtime_failures],
            "commits_to_revert": list(self.commits_to_revert),
            "stable_ref": self.stable_ref,
            "restore_paths": list(self.restore_paths),
            "push": self.push,
            "remote": self.remote,
            "branch": self.branch,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RollbackResult:
    rollback_id: str
    task_id: str
    success: bool
    stage: RollbackStage
    decision: RollbackDecision
    actions: tuple[RollbackActionResult, ...] = ()
    notification: RollbackNotification | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollback_id": self.rollback_id,
            "task_id": self.task_id,
            "success": self.success,
            "stage": self.stage.value,
            "decision": self.decision.to_dict(),
            "actions": [action.to_dict() for action in self.actions],
            "notification": self.notification.to_dict() if self.notification else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class RollbackEngineConfig:
    fail_if_no_restore_target: bool = True
    push_after_rollback: bool = False
    allow_network: bool = True


class RollbackEngine:
    """Restores a repository to a safe state after automated failure signals."""

    def __init__(
        self,
        *,
        executor_pool: ExecutorWorkerPool | None = None,
        event_bus: EventBus | None = None,
        config: RollbackEngineConfig | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.executor_pool = executor_pool or ExecutorWorkerPool(max_workers=1, event_bus=self.event_bus)
        self.config = config or RollbackEngineConfig()

    async def run(self, request: RollbackRequest) -> RollbackResult:
        try:
            self._validate_request(request)
            decision = self.detect_failures(request)
            if not decision.required:
                result = RollbackResult(
                    rollback_id=request.rollback_id,
                    task_id=request.task_id,
                    success=True,
                    stage=RollbackStage.SKIPPED,
                    decision=decision,
                )
                await self._publish(request, RollbackStage.SKIPPED, "No rollback required", result.to_dict())
                return result

            await self._publish(request, RollbackStage.DETECTED, "Rollback required", decision.to_dict())
            actions = await self.rollback(request, decision)
            success = all(action.success for action in actions)
            notification = await self.notify_orchestrator(request, decision, actions, success)
            stage = RollbackStage.COMPLETED if success else RollbackStage.FAILED
            result = RollbackResult(
                rollback_id=request.rollback_id,
                task_id=request.task_id,
                success=success,
                stage=stage,
                decision=decision,
                actions=actions,
                notification=notification,
                error=None if success else "rollback failed",
            )
            await self._publish(
                request,
                stage,
                "Rollback completed" if success else "Rollback failed",
                result.to_dict(),
            )
            return result
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            decision = RollbackDecision(required=True, evidence=({"error": error},))
            result = RollbackResult(
                rollback_id=request.rollback_id,
                task_id=request.task_id,
                success=False,
                stage=RollbackStage.FAILED,
                decision=decision,
                error=error,
            )
            await self._publish(request, RollbackStage.FAILED, error, result.to_dict())
            return result

    def run_sync(self, request: RollbackRequest) -> RollbackResult:
        return asyncio.run(self.run(request))

    def detect_failures(self, request: RollbackRequest) -> RollbackDecision:
        reasons: list[RollbackReason] = []
        evidence: list[dict[str, Any]] = []

        if request.ci_cd_result is not None and not request.ci_cd_result.success:
            reason = self._ci_cd_reason(request.ci_cd_result)
            reasons.append(reason)
            evidence.append({"source": "ci_cd", "result": request.ci_cd_result.to_dict()})

        if request.self_review_result is not None:
            review = request.self_review_result
            if not review.approved or review.recommendation != SelfReviewRecommendation.APPROVE:
                reasons.append(RollbackReason.REVIEWER_REJECTION)
                evidence.append({"source": "self_review", "result": review.to_dict()})

        if request.rollback_signals:
            reasons.append(RollbackReason.REVIEWER_REJECTION)
            evidence.append({"source": "rollback_signals", "signals": [signal.to_dict() for signal in request.rollback_signals]})

        failed_runtime = tuple(failure for failure in request.runtime_failures if not failure.success)
        if failed_runtime:
            reasons.append(RollbackReason.RUNTIME_FAILURE)
            evidence.append({"source": "runtime", "failures": [failure.to_dict() for failure in failed_runtime]})

        unique_reasons = tuple(dict.fromkeys(reasons))
        return RollbackDecision(
            required=bool(unique_reasons),
            reasons=unique_reasons,
            strategy=self._strategy(request, bool(unique_reasons)),
            evidence=tuple(evidence),
        )

    async def rollback(self, request: RollbackRequest, decision: RollbackDecision) -> tuple[RollbackActionResult, ...]:
        commands = self._rollback_commands(request, decision)
        if not commands:
            if self.config.fail_if_no_restore_target:
                return (
                    RollbackActionResult(
                        name="rollback:missing-target",
                        stage=RollbackStage.FAILED,
                        command="",
                        success=False,
                        error="no rollback target configured",
                    ),
                )
            return ()

        actions: list[RollbackActionResult] = []
        for index, command in enumerate(commands, start=1):
            stage = RollbackStage.REVERTING if index == 1 else RollbackStage.RESTORING
            action = await self._run_command(request, f"rollback:{index:03d}", command, stage)
            actions.append(action)
            if not action.success:
                break
        return tuple(actions)

    async def notify_orchestrator(
        self,
        request: RollbackRequest,
        decision: RollbackDecision,
        actions: tuple[RollbackActionResult, ...],
        success: bool,
    ) -> RollbackNotification:
        payload = {
            "rollback_id": request.rollback_id,
            "task_id": request.task_id,
            "success": success,
            "decision": decision.to_dict(),
            "actions": [action.to_dict() for action in actions],
        }
        notification = RollbackNotification(
            sent=True,
            task_id=request.task_id,
            message="rollback_completed" if success else "rollback_failed",
            payload=payload,
        )
        await self._publish(request, RollbackStage.NOTIFYING, notification.message, payload)
        return notification

    def _rollback_commands(self, request: RollbackRequest, decision: RollbackDecision) -> tuple[str, ...]:
        commands: list[str] = []
        if decision.strategy == RollbackStrategy.REVERT_COMMITS:
            commits = " ".join(shlex.quote(commit) for commit in request.commits_to_revert)
            commands.append(f"git revert --no-edit {commits}")
        elif decision.strategy == RollbackStrategy.RESTORE_STABLE_REF and request.stable_ref:
            commands.append(f"git reset --hard {shlex.quote(request.stable_ref)}")

        if request.restore_paths and request.stable_ref:
            paths = " ".join(shlex.quote(path) for path in request.restore_paths)
            commands.append(f"git checkout {shlex.quote(request.stable_ref)} -- {paths}")

        if request.push or self.config.push_after_rollback:
            branch = request.branch or "HEAD"
            commands.append(f"git push {shlex.quote(request.remote)} {shlex.quote(branch)}")
        return tuple(commands)

    async def _run_command(
        self,
        request: RollbackRequest,
        node_suffix: str,
        command: str,
        stage: RollbackStage,
    ) -> RollbackActionResult:
        await self._publish(request, stage, f"Running rollback command {node_suffix}", {"command": command})
        node = TaskGraphNode(
            id=f"{request.rollback_id}:{node_suffix}",
            type=TaskGraphNodeType.EXECUTE,
            payload={
                "task_id": request.task_id,
                "tool": "run_command",
                "input": {
                    "cmd": command,
                    "cwd": request.repo_path,
                    "allow_network": self.config.allow_network,
                },
                "lock_key": f"git:{request.repo_path}",
            },
        )
        result = await self.executor_pool.node_runner(node)
        return RollbackActionResult(
            name=node_suffix,
            stage=stage,
            command=command,
            success=result.success,
            output=result.output,
            error=result.error,
        )

    def _ci_cd_reason(self, result: CICDResult) -> RollbackReason:
        failed_test = any(not check.success and check.stage == CICDStage.TESTING for check in result.checks)
        if failed_test or "test" in (result.error or "").lower():
            return RollbackReason.TEST_FAILURE
        if result.stage in {CICDStage.FAILED, CICDStage.DEPLOYING, CICDStage.DEPLOYED}:
            return RollbackReason.DEPLOYMENT_FAILURE
        return RollbackReason.RUNTIME_FAILURE

    def _strategy(self, request: RollbackRequest, required: bool) -> RollbackStrategy:
        if not required:
            return RollbackStrategy.SIGNAL_ONLY
        if request.commits_to_revert:
            return RollbackStrategy.REVERT_COMMITS
        if request.stable_ref:
            return RollbackStrategy.RESTORE_STABLE_REF
        return RollbackStrategy.SIGNAL_ONLY

    def _validate_request(self, request: RollbackRequest) -> None:
        if not request.rollback_id.strip():
            raise ValueError("rollback_id is required")
        if not request.task_id.strip():
            raise ValueError("task_id is required")
        if not request.repo_path.strip():
            raise ValueError("repo_path is required")

    async def _publish(
        self,
        request: RollbackRequest,
        stage: RollbackStage,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event_type = EventType.TASK_FAILED if stage == RollbackStage.FAILED else EventType.TASK_STATE_CHANGED
        published = self.event_bus.publish(
            OrchestrationEvent(
                event_type=event_type,
                task_id=request.task_id,
                message=message,
                payload={
                    "rollback_id": request.rollback_id,
                    "stage": stage.value,
                    **(payload or {}),
                },
            )
        )
        if isawaitable(published):
            await published


__all__ = [
    "RollbackActionResult",
    "RollbackDecision",
    "RollbackEngine",
    "RollbackEngineConfig",
    "RollbackNotification",
    "RollbackReason",
    "RollbackRequest",
    "RollbackResult",
    "RollbackStage",
    "RollbackStrategy",
    "RuntimeFailureSignal",
]
