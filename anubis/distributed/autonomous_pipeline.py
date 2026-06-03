"""Continuous autonomous improvement pipeline for ANUBIS DEVIN++."""

from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass, field
from enum import StrEnum
from inspect import isawaitable
from typing import Any

from anubis.distributed.ci_cd_engine import CICDEngine, CICDRequest, CICDResult, PullRequestSignal
from anubis.distributed.company_runtime import AutonomousCompanyRuntime, CompanyCycleResult, CompanyRuntimeStage, CompanyTaskResult
from anubis.distributed.contracts import EventType, OrchestrationEvent
from anubis.distributed.event_bus import EventBus
from anubis.distributed.rollback_engine import RollbackEngine, RollbackRequest, RollbackResult, RuntimeFailureSignal


class AutonomousPipelineStage(StrEnum):
    DETECTING = "detecting"
    ORCHESTRATING = "orchestrating"
    CI_VALIDATING = "ci_validating"
    DEPLOYING = "deploying"
    ROLLING_BACK = "rolling_back"
    COMPLETED = "completed"
    FAILED = "failed"
    IDLE = "idle"
    STOPPED = "stopped"


@dataclass(frozen=True)
class PipelineTaskResult:
    task_result: CompanyTaskResult
    ci_cd_result: CICDResult | None = None
    rollback_result: RollbackResult | None = None

    @property
    def success(self) -> bool:
        if self.rollback_result is not None:
            return self.rollback_result.success
        if self.ci_cd_result is not None:
            return self.ci_cd_result.success
        return self.task_result.success

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_result": self.task_result.to_dict(),
            "ci_cd_result": self.ci_cd_result.to_dict() if self.ci_cd_result else None,
            "rollback_result": self.rollback_result.to_dict() if self.rollback_result else None,
            "success": self.success,
        }


@dataclass(frozen=True)
class AutonomousPipelineCycleResult:
    cycle_id: str
    success: bool
    stage: AutonomousPipelineStage
    company_result: CompanyCycleResult | None = None
    task_results: tuple[PipelineTaskResult, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "success": self.success,
            "stage": self.stage.value,
            "company_result": self.company_result.to_dict() if self.company_result else None,
            "task_results": [result.to_dict() for result in self.task_results],
            "error": self.error,
        }


@dataclass(frozen=True)
class AutonomousPipelineConfig:
    cycle_interval_seconds: float = 60.0
    max_cycles: int | None = None
    ci_test_commands: tuple[str, ...] = ()
    ci_static_commands: tuple[str, ...] = ()
    deploy_commands: tuple[str, ...] = ()
    rollback_stable_ref: str | None = "HEAD~1"
    rollback_push: bool = False
    deployment_environment: str = "production"


class AutonomousPipeline:
    """Runs ANUBIS as a safe, reversible, never-ending improvement pipeline."""

    def __init__(
        self,
        *,
        company_runtime: AutonomousCompanyRuntime | None = None,
        ci_cd_engine: CICDEngine | None = None,
        rollback_engine: RollbackEngine | None = None,
        event_bus: EventBus | None = None,
        config: AutonomousPipelineConfig | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.company_runtime = company_runtime or AutonomousCompanyRuntime(event_bus=self.event_bus)
        self.ci_cd_engine = ci_cd_engine or CICDEngine(event_bus=self.event_bus)
        self.rollback_engine = rollback_engine or RollbackEngine(event_bus=self.event_bus)
        self.config = config or AutonomousPipelineConfig()
        self._stop_requested = False
        self._cycle_counter = itertools.count(1)

    async def run_once(self, cycle_id: str | None = None) -> AutonomousPipelineCycleResult:
        cycle = cycle_id or f"autonomous-pipeline-{next(self._cycle_counter):06d}"
        try:
            await self._publish(cycle, AutonomousPipelineStage.DETECTING, "Starting autonomous improvement cycle")
            await self._publish(cycle, AutonomousPipelineStage.ORCHESTRATING, "Running distributed orchestration cycle")
            company_result = await self.company_runtime.run_once(cycle)
            if company_result.stage == CompanyRuntimeStage.IDLE:
                result = AutonomousPipelineCycleResult(
                    cycle_id=cycle,
                    success=True,
                    stage=AutonomousPipelineStage.IDLE,
                    company_result=company_result,
                )
                await self._publish(cycle, AutonomousPipelineStage.IDLE, "No autonomous work detected", result.to_dict())
                return result

            pipeline_results = []
            for task_result in company_result.task_results:
                pipeline_results.append(await self._process_task_result(cycle, task_result))

            success = all(result.success for result in pipeline_results) if pipeline_results else company_result.success
            stage = AutonomousPipelineStage.COMPLETED if success else AutonomousPipelineStage.FAILED
            result = AutonomousPipelineCycleResult(
                cycle_id=cycle,
                success=success,
                stage=stage,
                company_result=company_result,
                task_results=tuple(pipeline_results),
                error=None if success else "autonomous pipeline cycle failed",
            )
            await self._publish(
                cycle,
                stage,
                "Autonomous pipeline cycle completed" if success else "Autonomous pipeline cycle failed",
                result.to_dict(),
            )
            return result
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            result = AutonomousPipelineCycleResult(
                cycle_id=cycle,
                success=False,
                stage=AutonomousPipelineStage.FAILED,
                error=error,
            )
            await self._publish(cycle, AutonomousPipelineStage.FAILED, error, result.to_dict())
            return result

    async def run_forever(self, *, max_cycles: int | None = None) -> tuple[AutonomousPipelineCycleResult, ...]:
        results: list[AutonomousPipelineCycleResult] = []
        self._stop_requested = False
        limit = self.config.max_cycles if max_cycles is None else max_cycles
        while not self._stop_requested:
            if limit is not None and len(results) >= limit:
                break
            results.append(await self.run_once())
            if self._stop_requested:
                break
            await asyncio.sleep(self.config.cycle_interval_seconds)
        if self._stop_requested:
            await self._publish(
                "autonomous-pipeline",
                AutonomousPipelineStage.STOPPED,
                "Autonomous pipeline stopped by supervisor",
            )
        return tuple(results)

    def run_once_sync(self, cycle_id: str | None = None) -> AutonomousPipelineCycleResult:
        return asyncio.run(self.run_once(cycle_id))

    def stop(self) -> None:
        self._stop_requested = True

    async def _process_task_result(self, cycle_id: str, task_result: CompanyTaskResult) -> PipelineTaskResult:
        if not task_result.success:
            rollback = await self._rollback_failed_task(cycle_id, task_result, None)
            return PipelineTaskResult(task_result=task_result, rollback_result=rollback)

        if task_result.pr_result is None:
            return PipelineTaskResult(task_result=task_result)

        await self._publish(task_result.task.task_id, AutonomousPipelineStage.CI_VALIDATING, "Running CI/CD validation")
        ci_result = await self.ci_cd_engine.run(self._ci_cd_request(cycle_id, task_result))
        if ci_result.success:
            await self._publish(task_result.task.task_id, AutonomousPipelineStage.DEPLOYING, "CI/CD deployment completed", ci_result.to_dict())
            return PipelineTaskResult(task_result=task_result, ci_cd_result=ci_result)

        rollback = await self._rollback_failed_task(cycle_id, task_result, ci_result)
        return PipelineTaskResult(task_result=task_result, ci_cd_result=ci_result, rollback_result=rollback)

    async def _rollback_failed_task(
        self,
        cycle_id: str,
        task_result: CompanyTaskResult,
        ci_result: CICDResult | None,
    ) -> RollbackResult:
        await self._publish(task_result.task.task_id, AutonomousPipelineStage.ROLLING_BACK, "Triggering rollback for unsafe task")
        return await self.rollback_engine.run(self._rollback_request(cycle_id, task_result, ci_result))

    def _ci_cd_request(self, cycle_id: str, task_result: CompanyTaskResult) -> CICDRequest:
        repo_path = self._repo_path(task_result)
        payload = task_result.pr_result.payload if task_result.pr_result else None
        pr_signal = PullRequestSignal(
            pipeline_id=f"{cycle_id}:{task_result.task.task_id}:ci",
            repo_path=repo_path,
            title=payload.title if payload else task_result.task.requirement,
            head_branch=payload.head_branch if payload else "",
            base_branch=payload.base_branch if payload else "main",
            metadata={"company_task": task_result.task.to_dict()},
        )
        return CICDRequest(
            pipeline_id=pr_signal.pipeline_id,
            repo_path=repo_path,
            pr_signal=pr_signal,
            pr_result=task_result.pr_result,
            self_review_result=task_result.self_review_result,
            git_result=task_result.git_result,
            test_commands=self._test_commands(task_result),
            static_commands=self.config.ci_static_commands,
            deploy_commands=self.config.deploy_commands,
            deployment_environment=self.config.deployment_environment,
            metadata={"cycle_id": cycle_id, "task_result": task_result.to_dict()},
        )

    def _rollback_request(
        self,
        cycle_id: str,
        task_result: CompanyTaskResult,
        ci_result: CICDResult | None,
    ) -> RollbackRequest:
        return RollbackRequest(
            rollback_id=f"{cycle_id}:{task_result.task.task_id}:rollback",
            task_id=task_result.task.task_id,
            repo_path=self._repo_path(task_result),
            ci_cd_result=ci_result,
            self_review_result=task_result.self_review_result,
            runtime_failures=self._runtime_failures(task_result),
            stable_ref=self.config.rollback_stable_ref,
            push=self.config.rollback_push,
            metadata={"cycle_id": cycle_id, "task_result": task_result.to_dict()},
        )

    def _runtime_failures(self, task_result: CompanyTaskResult) -> tuple[RuntimeFailureSignal, ...]:
        if task_result.success:
            return ()
        if task_result.self_review_result is not None and not task_result.self_review_result.approved:
            return ()
        return (
            RuntimeFailureSignal(
                name="orchestrator_execution",
                success=False,
                error=task_result.error or "orchestrator task failed",
            ),
        )

    def _test_commands(self, task_result: CompanyTaskResult) -> tuple[str, ...]:
        if self.config.ci_test_commands:
            return self.config.ci_test_commands
        improvement_task = task_result.task.improvement_task
        if improvement_task and improvement_task.test_commands:
            return improvement_task.test_commands
        repo = task_result.task.repo
        command = repo.metadata.get("test_command") if repo else None
        return (command,) if isinstance(command, str) and command.strip() else ()

    def _repo_path(self, task_result: CompanyTaskResult) -> str:
        if task_result.task.repo is not None:
            return task_result.task.repo.path
        if task_result.task.improvement_task is not None:
            return task_result.task.improvement_task.repo.path
        return "."

    async def _publish(
        self,
        task_id: str,
        stage: AutonomousPipelineStage,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event_type = EventType.TASK_FAILED if stage == AutonomousPipelineStage.FAILED else EventType.TASK_STATE_CHANGED
        published = self.event_bus.publish(
            OrchestrationEvent(
                event_type=event_type,
                task_id=task_id,
                message=message,
                payload={"stage": stage.value, **(payload or {})},
            )
        )
        if isawaitable(published):
            await published


__all__ = [
    "AutonomousPipeline",
    "AutonomousPipelineConfig",
    "AutonomousPipelineCycleResult",
    "AutonomousPipelineStage",
    "PipelineTaskResult",
]
