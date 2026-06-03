import unittest

from anubis.distributed import (
    CICDCommandResult,
    CICDDecision,
    CICDResult,
    CICDStage,
    EventBus,
    EventType,
    ExecutionResult,
    ExecutorWorkerPool,
    LogicValidationReport,
    RollbackEngine,
    RollbackReason,
    RollbackRequest,
    RollbackSignal,
    RollbackStage,
    RollbackStrategy,
    RuntimeFailureSignal,
    SelfReviewRecommendation,
    SelfReviewResult,
    SelfReviewRisk,
    SelfReviewStage,
    StaticAnalysisReport,
)


class RollbackExecutor:
    calls: list[tuple[str, str, dict]] = []
    fail_revert: bool = False

    def execute(self, step):
        step_id = step["step_id"]
        tool = step["tool"]
        tool_input = dict(step.get("input", {}))
        command = tool_input.get("cmd", "")
        type(self).calls.append((step_id, tool, tool_input))
        if "git revert" in command and type(self).fail_revert:
            return ExecutionResult(step_id=step_id, success=False, output="revert failed", logs=("rollback",))
        return ExecutionResult(step_id=step_id, success=True, output=f"ran {command}", logs=("rollback",))


def failed_test_ci() -> CICDResult:
    return CICDResult(
        pipeline_id="pipeline-001",
        success=False,
        stage=CICDStage.REJECTED,
        decision=CICDDecision.REJECT,
        checks=(
            CICDCommandResult(
                name="test:001",
                stage=CICDStage.TESTING,
                command="pytest tests",
                success=False,
                output="failed",
            ),
        ),
        error="test gate failed",
    )


def rejected_review() -> SelfReviewResult:
    return SelfReviewResult(
        task_id="task-001",
        approved=False,
        recommendation=SelfReviewRecommendation.REJECT,
        risk=SelfReviewRisk.HIGH,
        stage=SelfReviewStage.REJECTED,
        static_analysis=StaticAnalysisReport(success=False),
        logic_validation=LogicValidationReport(valid=False, matched_terms=(), missing_terms=("auth",), evidence=()),
        issues=("unsafe change",),
    )


def request(**overrides) -> RollbackRequest:
    values = {
        "rollback_id": "rollback-001",
        "task_id": "task-001",
        "repo_path": "/repos/api",
        "commits_to_revert": ("abc123",),
        "ci_cd_result": failed_test_ci(),
    }
    values.update(overrides)
    return RollbackRequest(**values)


class RollbackEngineTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        RollbackExecutor.calls = []
        RollbackExecutor.fail_revert = False
        self.event_bus = EventBus()
        self.engine = RollbackEngine(
            executor_pool=ExecutorWorkerPool(max_workers=1, executor_factory=RollbackExecutor, event_bus=self.event_bus),
            event_bus=self.event_bus,
        )

    async def asyncTearDown(self) -> None:
        await self.event_bus.drain()
        self.event_bus.close()

    async def test_rollback_engine_reverts_commit_for_failed_tests_and_notifies(self) -> None:
        events = []
        self.event_bus.subscribe(None, events.append)

        result = await self.engine.run(request())
        await self.event_bus.drain()

        self.assertTrue(result.success)
        self.assertEqual(result.stage, RollbackStage.COMPLETED)
        self.assertEqual(result.decision.strategy, RollbackStrategy.REVERT_COMMITS)
        self.assertEqual(result.decision.reasons, (RollbackReason.TEST_FAILURE,))
        self.assertEqual([call[2]["cmd"] for call in RollbackExecutor.calls], ["git revert --no-edit abc123"])
        self.assertTrue(result.notification.sent)
        self.assertIn(EventType.TASK_STATE_CHANGED, [event.event_type for event in events])

    async def test_rollback_engine_restores_stable_ref_for_runtime_failure(self) -> None:
        result = await self.engine.run(
            request(
                ci_cd_result=None,
                commits_to_revert=(),
                stable_ref="stable/main",
                runtime_failures=(RuntimeFailureSignal(name="healthcheck", success=False, error="500"),),
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.decision.strategy, RollbackStrategy.RESTORE_STABLE_REF)
        self.assertEqual(result.decision.reasons, (RollbackReason.RUNTIME_FAILURE,))
        self.assertEqual([call[2]["cmd"] for call in RollbackExecutor.calls], ["git reset --hard stable/main"])

    async def test_rollback_engine_detects_reviewer_rejection_and_restore_paths(self) -> None:
        result = await self.engine.run(
            request(
                ci_cd_result=None,
                self_review_result=rejected_review(),
                commits_to_revert=(),
                stable_ref="HEAD~2",
                restore_paths=("service.py", "tests/test_service.py"),
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.decision.reasons, (RollbackReason.REVIEWER_REJECTION,))
        self.assertEqual(
            [call[2]["cmd"] for call in RollbackExecutor.calls],
            ["git reset --hard 'HEAD~2'", "git checkout 'HEAD~2' -- service.py tests/test_service.py"],
        )

    async def test_rollback_engine_consumes_reviewer_rollback_signals(self) -> None:
        result = await self.engine.run(
            request(
                ci_cd_result=None,
                rollback_signals=(RollbackSignal(step_id="verify-001", reason="checksum mismatch"),),
                commits_to_revert=("def456",),
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.decision.reasons, (RollbackReason.REVIEWER_REJECTION,))
        self.assertEqual([call[2]["cmd"] for call in RollbackExecutor.calls], ["git revert --no-edit def456"])

    async def test_rollback_engine_skips_when_no_failure_detected(self) -> None:
        result = await self.engine.run(request(ci_cd_result=None, commits_to_revert=(), stable_ref=None))

        self.assertTrue(result.success)
        self.assertEqual(result.stage, RollbackStage.SKIPPED)
        self.assertEqual(RollbackExecutor.calls, [])

    async def test_rollback_engine_reports_failed_revert(self) -> None:
        RollbackExecutor.fail_revert = True

        result = await self.engine.run(request())

        self.assertFalse(result.success)
        self.assertEqual(result.stage, RollbackStage.FAILED)
        self.assertEqual(result.error, "rollback failed")
        self.assertFalse(result.actions[0].success)


if __name__ == "__main__":
    unittest.main()
