import unittest

from anubis.distributed import (
    AutonomousCompanyRuntime,
    BranchPlan,
    CommitPlan,
    CompanyRuntimeConfig,
    CompanyRuntimeStage,
    DiffAnalysis,
    EventBus,
    EventType,
    ExecutionResult,
    ExecutorWorkerPool,
    FeatureEngineResult,
    FeatureStage,
    GitAutonomyResult,
    GitStage,
    ImprovementCandidate,
    ImprovementEngineConfig,
    ImprovementKind,
    ImprovementRisk,
    MultiRepoOrchestrator,
    PRGenerationResult,
    PRStage,
    RepoRegistry,
    RepoRole,
    RepositoryMetadata,
    SelfReviewRecommendation,
    SelfReviewResult,
    SelfReviewRisk,
    SelfReviewStage,
    StaticAnalysisReport,
    LogicValidationReport,
)


class RuntimeExecutor:
    calls: list[tuple[str, str, dict]] = []
    fail_deploy: bool = False

    def execute(self, step):
        step_id = step["step_id"]
        tool = step["tool"]
        tool_input = dict(step.get("input", {}))
        type(self).calls.append((step_id, tool, tool_input))
        if tool == "search_codebase":
            return ExecutionResult(step_id=step_id, success=True, output="api/auth.py missing tests coverage gap", logs=("scan",))
        if "deploy-check" in tool_input.get("cmd", "") and type(self).fail_deploy:
            return ExecutionResult(step_id=step_id, success=False, output="deploy failed", logs=("fail",))
        return ExecutionResult(step_id=step_id, success=True, output=f"ran {tool_input.get('cmd', tool)}", logs=("ok",))


class FakeFeatureEngine:
    calls = []

    async def run(self, request):
        self.calls.append(request)
        return FeatureEngineResult(feature_id=request.feature_id, success=True, stage=FeatureStage.COMPLETED)


class FakeGitAgent:
    calls = []

    async def run(self, request):
        self.calls.append(request)
        return GitAutonomyResult(
            task_id=request.task_id,
            success=True,
            stage=GitStage.PUSHED,
            branch=BranchPlan(name=f"anubis/task/{request.task_id}", base_branch=None, command="git checkout"),
            diff=DiffAnalysis(
                changed_files=("api/auth.py",),
                additions=4,
                deletions=1,
                risk="low",
                summary="1 file(s), +4/-1, risk=low",
                raw="diff --git a/api/auth.py b/api/auth.py",
            ),
            commits=(
                CommitPlan(
                    message="test(api): add auth regression tests",
                    paths=("api/auth.py",),
                    stage_command="git add -- api/auth.py",
                    commit_command="git commit -m test",
                ),
            ),
            push_result={"success": True},
        )


class FakeSelfReviewer:
    calls = []
    approve = True

    async def run(self, request):
        self.calls.append(request)
        return SelfReviewResult(
            task_id=request.task_id,
            approved=self.approve,
            recommendation=SelfReviewRecommendation.APPROVE if self.approve else SelfReviewRecommendation.REJECT,
            risk=SelfReviewRisk.LOW,
            stage=SelfReviewStage.APPROVED if self.approve else SelfReviewStage.REJECTED,
            static_analysis=StaticAnalysisReport(success=True),
            logic_validation=LogicValidationReport(valid=True, matched_terms=("auth",), missing_terms=(), evidence=("auth",)),
            issues=() if self.approve else ("rejected",),
        )


class FakePRGenerator:
    calls = []

    async def run(self, request):
        self.calls.append(request)
        return PRGenerationResult(task_id=request.task_id, success=True, stage=PRStage.CREATED)


def registry() -> RepoRegistry:
    return RepoRegistry(
        (
            RepositoryMetadata(
                repo_id="api",
                name="anubis-api",
                path="/repos/api",
                language="python",
                structure=("backend/routes",),
                role=RepoRole.BACKEND,
                tags=("auth",),
                metadata={"test_command": "pytest tests/api"},
            ),
        )
    )


class CompanyRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        RuntimeExecutor.calls = []
        RuntimeExecutor.fail_deploy = False
        FakeFeatureEngine.calls = []
        FakeGitAgent.calls = []
        FakeSelfReviewer.calls = []
        FakeSelfReviewer.approve = True
        FakePRGenerator.calls = []
        self.event_bus = EventBus()

    async def asyncTearDown(self) -> None:
        await self.event_bus.drain()
        self.event_bus.close()

    def runtime(self) -> AutonomousCompanyRuntime:
        return AutonomousCompanyRuntime(
            repo_orchestrator=MultiRepoOrchestrator(registry=registry()),
            feature_engine=FakeFeatureEngine(),
            git_agent=FakeGitAgent(),
            self_reviewer=FakeSelfReviewer(),
            pr_generator=FakePRGenerator(),
            executor_pool=ExecutorWorkerPool(max_workers=2, executor_factory=RuntimeExecutor, event_bus=self.event_bus),
            event_bus=self.event_bus,
            config=CompanyRuntimeConfig(cycle_interval_seconds=0, max_tasks_per_cycle=1, deploy_validation_commands=("deploy-check",)),
        )

    async def test_company_runtime_runs_full_autonomous_cycle(self) -> None:
        runtime = self.runtime()
        events = []
        self.event_bus.subscribe(None, events.append)

        result = await runtime.run_once("company-001")
        await self.event_bus.drain()

        self.assertTrue(result.success)
        self.assertEqual(result.stage, CompanyRuntimeStage.COMPLETED)
        self.assertEqual(len(result.detected_tasks), 1)
        task_result = result.task_results[0]
        self.assertTrue(task_result.success)
        self.assertTrue(task_result.deploy_validation.success)
        self.assertTrue(FakeFeatureEngine.calls)
        self.assertTrue(FakeGitAgent.calls)
        self.assertTrue(FakeSelfReviewer.calls)
        self.assertTrue(FakePRGenerator.calls)
        self.assertIn("deploy-check", [call[2]["cmd"] for call in RuntimeExecutor.calls if call[1] == "run_command"])
        self.assertIn(EventType.TASK_STATE_CHANGED, [event.event_type for event in events])

    async def test_company_runtime_marks_cycle_failed_when_deploy_validation_fails(self) -> None:
        RuntimeExecutor.fail_deploy = True
        runtime = self.runtime()

        result = await runtime.run_once("company-002")

        self.assertFalse(result.success)
        self.assertEqual(result.stage, CompanyRuntimeStage.FAILED)
        self.assertEqual(result.task_results[0].error, "deploy-ready validation failed")

    async def test_company_runtime_run_forever_can_be_bounded_for_supervision(self) -> None:
        runtime = self.runtime()

        results = await runtime.run_forever(max_cycles=2)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.stage == CompanyRuntimeStage.COMPLETED for result in results))


if __name__ == "__main__":
    unittest.main()
