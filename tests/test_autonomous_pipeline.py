import unittest

from anubis.distributed import (
    AutonomousPipeline,
    AutonomousPipelineConfig,
    AutonomousPipelineStage,
    CICDDecision,
    CICDResult,
    CICDStage,
    CompanyCycleResult,
    CompanyRuntimeStage,
    CompanyTask,
    CompanyTaskResult,
    EventBus,
    EventType,
    GitAutonomyResult,
    GitStage,
    LogicValidationReport,
    PRGenerationResult,
    PRStage,
    PullRequestPayload,
    RepositoryMetadata,
    RollbackDecision,
    RollbackReason,
    RollbackResult,
    RollbackStage,
    RollbackStrategy,
    SelfReviewRecommendation,
    SelfReviewResult,
    SelfReviewRisk,
    SelfReviewStage,
    StaticAnalysisReport,
)


def repo() -> RepositoryMetadata:
    return RepositoryMetadata(
        repo_id="api",
        name="api",
        path="/repos/api",
        language="python",
        metadata={"test_command": "pytest tests/api"},
    )


def self_review(approved=True) -> SelfReviewResult:
    return SelfReviewResult(
        task_id="task-001",
        approved=approved,
        recommendation=SelfReviewRecommendation.APPROVE if approved else SelfReviewRecommendation.REJECT,
        risk=SelfReviewRisk.LOW if approved else SelfReviewRisk.HIGH,
        stage=SelfReviewStage.APPROVED if approved else SelfReviewStage.REJECTED,
        static_analysis=StaticAnalysisReport(success=approved),
        logic_validation=LogicValidationReport(valid=approved, matched_terms=("api",), missing_terms=(), evidence=("api",)),
        issues=() if approved else ("rejected",),
    )


def pr_result() -> PRGenerationResult:
    return PRGenerationResult(
        task_id="task-001",
        success=True,
        stage=PRStage.CREATED,
        payload=PullRequestPayload(
            title="Improve API tests",
            body="Autonomous improvement",
            head_branch="anubis/task/task-001",
            base_branch="main",
        ),
    )


def successful_task() -> CompanyTaskResult:
    task = CompanyTask(task_id="task-001", requirement="Improve API tests", repo=repo())
    return CompanyTaskResult(
        task=task,
        success=True,
        git_result=GitAutonomyResult(task_id="task-001", success=True, stage=GitStage.PUSHED),
        self_review_result=self_review(),
        pr_result=pr_result(),
    )


def failed_review_task() -> CompanyTaskResult:
    task = CompanyTask(task_id="task-001", requirement="Improve API tests", repo=repo())
    return CompanyTaskResult(
        task=task,
        success=False,
        self_review_result=self_review(False),
        error="self-review rejected task",
    )


class FakeCompanyRuntime:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def run_once(self, cycle_id=None):
        self.calls.append(cycle_id)
        return self.result


class FakeCICD:
    def __init__(self, success=True):
        self.success = success
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        return CICDResult(
            pipeline_id=request.pipeline_id,
            success=self.success,
            stage=CICDStage.DEPLOYED if self.success else CICDStage.REJECTED,
            decision=CICDDecision.APPROVE if self.success else CICDDecision.REJECT,
            error=None if self.success else "test gate failed",
        )


class FakeRollback:
    def __init__(self, success=True):
        self.success = success
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        return RollbackResult(
            rollback_id=request.rollback_id,
            task_id=request.task_id,
            success=self.success,
            stage=RollbackStage.COMPLETED if self.success else RollbackStage.FAILED,
            decision=RollbackDecision(
                required=True,
                reasons=(RollbackReason.TEST_FAILURE,),
                strategy=RollbackStrategy.RESTORE_STABLE_REF,
            ),
            error=None if self.success else "rollback failed",
        )


class AutonomousPipelineTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.event_bus = EventBus()

    async def asyncTearDown(self) -> None:
        await self.event_bus.drain()
        self.event_bus.close()

    def pipeline(self, company_result, ci_success=True, rollback_success=True):
        ci = FakeCICD(ci_success)
        rollback = FakeRollback(rollback_success)
        pipeline = AutonomousPipeline(
            company_runtime=FakeCompanyRuntime(company_result),
            ci_cd_engine=ci,
            rollback_engine=rollback,
            event_bus=self.event_bus,
            config=AutonomousPipelineConfig(cycle_interval_seconds=0, deploy_commands=("deploy production",)),
        )
        return pipeline, ci, rollback

    async def test_pipeline_runs_pr_through_ci_and_deploys(self) -> None:
        company = CompanyCycleResult(
            cycle_id="cycle-001",
            success=True,
            stage=CompanyRuntimeStage.COMPLETED,
            task_results=(successful_task(),),
        )
        events = []
        self.event_bus.subscribe(None, events.append)
        pipeline, ci, rollback = self.pipeline(company)

        result = await pipeline.run_once("cycle-001")
        await self.event_bus.drain()

        self.assertTrue(result.success)
        self.assertEqual(result.stage, AutonomousPipelineStage.COMPLETED)
        self.assertEqual(len(ci.requests), 1)
        self.assertEqual(ci.requests[0].deploy_commands, ("deploy production",))
        self.assertEqual(rollback.requests, [])
        self.assertIn(EventType.TASK_STATE_CHANGED, [event.event_type for event in events])

    async def test_pipeline_rolls_back_failed_ci(self) -> None:
        company = CompanyCycleResult(
            cycle_id="cycle-002",
            success=True,
            stage=CompanyRuntimeStage.COMPLETED,
            task_results=(successful_task(),),
        )
        pipeline, ci, rollback = self.pipeline(company, ci_success=False)

        result = await pipeline.run_once("cycle-002")

        self.assertTrue(result.success)
        self.assertEqual(result.stage, AutonomousPipelineStage.COMPLETED)
        self.assertEqual(len(ci.requests), 1)
        self.assertEqual(len(rollback.requests), 1)
        self.assertEqual(rollback.requests[0].ci_cd_result.error, "test gate failed")

    async def test_pipeline_rolls_back_reviewer_rejection_from_orchestrator(self) -> None:
        company = CompanyCycleResult(
            cycle_id="cycle-003",
            success=False,
            stage=CompanyRuntimeStage.FAILED,
            task_results=(failed_review_task(),),
        )
        pipeline, ci, rollback = self.pipeline(company)

        result = await pipeline.run_once("cycle-003")

        self.assertTrue(result.success)
        self.assertEqual(ci.requests, [])
        self.assertEqual(len(rollback.requests), 1)
        self.assertFalse(rollback.requests[0].self_review_result.approved)

    async def test_pipeline_can_run_bounded_forever_loop(self) -> None:
        company = CompanyCycleResult(
            cycle_id="cycle-loop",
            success=True,
            stage=CompanyRuntimeStage.COMPLETED,
            task_results=(successful_task(),),
        )
        pipeline, ci, _rollback = self.pipeline(company)

        results = await pipeline.run_forever(max_cycles=2)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.success for result in results))
        self.assertEqual(len(ci.requests), 2)

    async def test_pipeline_reports_idle_cycle_without_ci_or_rollback(self) -> None:
        company = CompanyCycleResult(cycle_id="cycle-idle", success=True, stage=CompanyRuntimeStage.IDLE)
        pipeline, ci, rollback = self.pipeline(company)

        result = await pipeline.run_once("cycle-idle")

        self.assertTrue(result.success)
        self.assertEqual(result.stage, AutonomousPipelineStage.IDLE)
        self.assertEqual(ci.requests, [])
        self.assertEqual(rollback.requests, [])


if __name__ == "__main__":
    unittest.main()
