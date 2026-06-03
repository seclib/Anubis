import unittest

from anubis.distributed import (
    CICDEngine,
    CICDEngineConfig,
    CICDRequest,
    CICDStage,
    EventBus,
    EventType,
    ExecutionResult,
    ExecutorWorkerPool,
    LogicValidationReport,
    PRGenerationResult,
    PRStage,
    PullRequestSignal,
    SelfReviewRecommendation,
    SelfReviewResult,
    SelfReviewRisk,
    SelfReviewStage,
    StaticAnalysisReport,
)


class CICDExecutor:
    calls: list[tuple[str, str, dict]] = []
    fail_test: bool = False
    fail_static: bool = False
    fail_deploy: bool = False

    def execute(self, step):
        step_id = step["step_id"]
        tool = step["tool"]
        tool_input = dict(step.get("input", {}))
        command = tool_input.get("cmd", "")
        type(self).calls.append((step_id, tool, tool_input))

        if "pytest" in command and type(self).fail_test:
            return ExecutionResult(step_id=step_id, success=False, output="tests failed", logs=("test",))
        if "ruff" in command and type(self).fail_static:
            return ExecutionResult(step_id=step_id, success=False, output="static failed", logs=("static",))
        if "deploy" in command and type(self).fail_deploy:
            return ExecutionResult(step_id=step_id, success=False, output="deploy failed", logs=("deploy",))
        return ExecutionResult(step_id=step_id, success=True, output=f"ran {command}", logs=("ok",))


def approved_review(risk=SelfReviewRisk.LOW) -> SelfReviewResult:
    return SelfReviewResult(
        task_id="pipeline-001",
        approved=True,
        recommendation=SelfReviewRecommendation.APPROVE,
        risk=risk,
        stage=SelfReviewStage.APPROVED,
        static_analysis=StaticAnalysisReport(success=True),
        logic_validation=LogicValidationReport(valid=True, matched_terms=("ci",), missing_terms=(), evidence=("ci",)),
    )


def pr_result() -> PRGenerationResult:
    return PRGenerationResult(task_id="pipeline-001", success=True, stage=PRStage.CREATED)


def request(**overrides) -> CICDRequest:
    values = {
        "pipeline_id": "pipeline-001",
        "repo_path": "/repos/api",
        "pr_signal": PullRequestSignal(
            pipeline_id="pipeline-001",
            repo_path="/repos/api",
            pr_number=42,
            title="Add CI gate",
            head_branch="anubis/task/pipeline-001",
        ),
        "pr_result": pr_result(),
        "self_review_result": approved_review(),
        "test_commands": ("pytest tests",),
        "static_commands": ("ruff check .",),
        "deploy_commands": ("deploy production",),
    }
    values.update(overrides)
    return CICDRequest(**values)


class CICDEngineTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        CICDExecutor.calls = []
        CICDExecutor.fail_test = False
        CICDExecutor.fail_static = False
        CICDExecutor.fail_deploy = False
        self.event_bus = EventBus()
        self.engine = CICDEngine(
            executor_pool=ExecutorWorkerPool(max_workers=2, executor_factory=CICDExecutor, event_bus=self.event_bus),
            event_bus=self.event_bus,
            config=CICDEngineConfig(default_deploy_commands=("deploy production",)),
        )

    async def asyncTearDown(self) -> None:
        await self.event_bus.drain()
        self.event_bus.close()

    async def test_ci_cd_engine_approves_and_deploys_safe_pr(self) -> None:
        events = []
        self.event_bus.subscribe(None, events.append)

        result = await self.engine.run(request())
        await self.event_bus.drain()

        self.assertTrue(result.success)
        self.assertTrue(result.approved)
        self.assertEqual(result.stage, CICDStage.DEPLOYED)
        self.assertTrue(result.deployment.success)
        self.assertEqual([call[2]["cmd"] for call in CICDExecutor.calls], ["pytest tests", "ruff check .", "deploy production"])
        self.assertIn(EventType.TASK_CREATED, [event.event_type for event in events])
        self.assertIn(EventType.TASK_COMPLETED, [event.event_type for event in events])

    async def test_ci_cd_engine_blocks_failed_tests_before_static_or_deploy(self) -> None:
        CICDExecutor.fail_test = True

        result = await self.engine.run(request())

        self.assertFalse(result.success)
        self.assertFalse(result.approved)
        self.assertEqual(result.stage, CICDStage.REJECTED)
        self.assertEqual(result.error, "test gate failed")
        self.assertEqual([call[2]["cmd"] for call in CICDExecutor.calls], ["pytest tests"])

    async def test_ci_cd_engine_requires_reviewer_output(self) -> None:
        result = await self.engine.run(request(self_review_result=None))

        self.assertFalse(result.success)
        self.assertEqual(result.stage, CICDStage.REJECTED)
        self.assertIn("missing self-review result", result.issues)
        self.assertNotIn("deploy production", [call[2]["cmd"] for call in CICDExecutor.calls])

    async def test_ci_cd_engine_blocks_high_risk_review(self) -> None:
        result = await self.engine.run(request(self_review_result=approved_review(SelfReviewRisk.HIGH)))

        self.assertFalse(result.success)
        self.assertEqual(result.stage, CICDStage.REJECTED)
        self.assertIn("high-risk code is blocked from automated deployment", result.issues)
        self.assertEqual([call[2]["cmd"] for call in CICDExecutor.calls], ["pytest tests", "ruff check ."])

    async def test_ci_cd_engine_reports_deployment_failure_after_approval(self) -> None:
        CICDExecutor.fail_deploy = True

        result = await self.engine.run(request())

        self.assertFalse(result.success)
        self.assertTrue(result.approved)
        self.assertEqual(result.stage, CICDStage.FAILED)
        self.assertEqual(result.error, "deployment gate failed")
        self.assertFalse(result.deployment.success)


if __name__ == "__main__":
    unittest.main()
