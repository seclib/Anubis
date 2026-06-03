import unittest

from anubis.distributed import (
    BranchPlan,
    CommitPlan,
    DiffAnalysis,
    EventBus,
    EventType,
    ExecutionResult,
    ExecutorWorkerPool,
    GitAutonomyResult,
    GitStage,
    SelfReviewEngine,
    SelfReviewRecommendation,
    SelfReviewRequest,
    SelfReviewRisk,
    SelfReviewStage,
    SelfReviewerConfig,
)


class RecordingSelfReviewExecutor:
    calls: list[tuple[str, str, dict]] = []
    fail_first_static: bool = False
    failed_once: bool = False

    def execute(self, step):
        step_id = step["step_id"]
        tool = step["tool"]
        tool_input = dict(step.get("input", {}))
        type(self).calls.append((step_id, tool, tool_input))

        command = tool_input.get("cmd", "")
        if command == "ruff check ." and type(self).fail_first_static and not type(self).failed_once:
            type(self).failed_once = True
            return ExecutionResult(step_id=step_id, success=False, output="lint failed", logs=("fail",))
        return ExecutionResult(step_id=step_id, success=True, output=f"ran {command}", logs=("ok",))


def git_result(*, raw: str, risk: str = "low") -> GitAutonomyResult:
    return GitAutonomyResult(
        task_id="feature-login",
        success=True,
        stage=GitStage.PUSHED,
        branch=BranchPlan(
            name="anubis/task/feature-login",
            base_branch=None,
            command="git checkout -B anubis/task/feature-login",
        ),
        diff=DiffAnalysis(
            changed_files=("api/auth.py",),
            additions=8,
            deletions=2,
            risk=risk,
            summary=f"1 file(s), +8/-2, risk={risk}",
            raw=raw,
        ),
        commits=(
            CommitPlan(
                message="feat(api): add login auth endpoint",
                paths=("api/auth.py",),
                stage_command="git add -- api/auth.py",
                commit_command="git commit -m 'feat(api): add login auth endpoint'",
            ),
        ),
        push_result={"success": True},
    )


CLEAN_DIFF = """diff --git a/api/auth.py b/api/auth.py
--- a/api/auth.py
+++ b/api/auth.py
@@ -1 +1,2 @@
-old
+def login_auth_endpoint():
+    return True
"""


class SelfReviewerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        RecordingSelfReviewExecutor.calls = []
        RecordingSelfReviewExecutor.fail_first_static = False
        RecordingSelfReviewExecutor.failed_once = False
        self.event_bus = EventBus()

    async def asyncTearDown(self) -> None:
        await self.event_bus.drain()
        self.event_bus.close()

    def engine(self, *, reject_on_high_risk: bool = True) -> SelfReviewEngine:
        return SelfReviewEngine(
            executor_pool=ExecutorWorkerPool(
                max_workers=1,
                executor_factory=RecordingSelfReviewExecutor,
                event_bus=self.event_bus,
            ),
            event_bus=self.event_bus,
            config=SelfReviewerConfig(
                default_static_commands=("ruff check .",),
                reject_on_high_risk=reject_on_high_risk,
            ),
        )

    async def test_self_review_approves_clean_matching_change(self) -> None:
        engine = self.engine()
        events = []
        self.event_bus.subscribe(None, events.append)

        result = await engine.run(
            SelfReviewRequest(
                task_id="feature-login",
                requirement="login auth endpoint",
                git_result=git_result(raw=CLEAN_DIFF),
                repo_path="/repos/anubis",
            )
        )
        await self.event_bus.drain()

        self.assertTrue(result.approved)
        self.assertEqual(result.recommendation, SelfReviewRecommendation.APPROVE)
        self.assertEqual(result.risk, SelfReviewRisk.LOW)
        self.assertEqual(result.stage, SelfReviewStage.APPROVED)
        self.assertTrue(result.static_analysis.success)
        self.assertTrue(result.logic_validation.valid)
        self.assertIn(EventType.TASK_STATE_CHANGED, [event.event_type for event in events])

    async def test_self_review_rejects_high_risk_bad_patterns(self) -> None:
        engine = self.engine()
        risky_diff = """diff --git a/api/auth.py b/api/auth.py
--- a/api/auth.py
+++ b/api/auth.py
@@ -1 +1,3 @@
+password = "secret"
+eval(user_input)
"""

        result = await engine.run(
            SelfReviewRequest(
                task_id="feature-login",
                requirement="login auth endpoint",
                git_result=git_result(raw=risky_diff),
                repo_path="/repos/anubis",
            )
        )

        self.assertFalse(result.approved)
        self.assertEqual(result.recommendation, SelfReviewRecommendation.REJECT)
        self.assertEqual(result.risk, SelfReviewRisk.HIGH)
        self.assertTrue(any("unsafe eval" in issue for issue in result.issues))
        self.assertTrue(any("hardcoded password" in issue for issue in result.issues))

    async def test_self_review_rejects_requirement_mismatch(self) -> None:
        engine = self.engine()

        result = await engine.run(
            SelfReviewRequest(
                task_id="feature-login",
                requirement="payment subscription invoice workflow",
                git_result=git_result(raw=CLEAN_DIFF),
                repo_path="/repos/anubis",
            )
        )

        self.assertFalse(result.approved)
        self.assertEqual(result.recommendation, SelfReviewRecommendation.REJECT)
        self.assertFalse(result.logic_validation.valid)
        self.assertIn("requirement coverage insufficient", "; ".join(result.issues))

    async def test_self_review_runs_fix_loop_then_approves(self) -> None:
        RecordingSelfReviewExecutor.fail_first_static = True
        engine = self.engine(reject_on_high_risk=False)

        result = await engine.run(
            SelfReviewRequest(
                task_id="feature-login",
                requirement="login auth endpoint",
                git_result=git_result(raw=CLEAN_DIFF),
                repo_path="/repos/anubis",
                static_commands=("ruff check .",),
                fix_commands=("ruff check . --fix",),
                max_fix_attempts=1,
            )
        )

        self.assertTrue(result.approved)
        self.assertEqual(result.fix_attempts, 1)
        commands = [call[2]["cmd"] for call in RecordingSelfReviewExecutor.calls]
        self.assertEqual(commands, ["ruff check .", "ruff check . --fix", "ruff check ."])
        self.assertTrue(result.fix_results[0]["success"])


if __name__ == "__main__":
    unittest.main()
