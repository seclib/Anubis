import unittest

from anubis.distributed import (
    AutonomousPRGenerator,
    BranchPlan,
    CommitPlan,
    DiffAnalysis,
    EventBus,
    EventType,
    ExecutionResult,
    ExecutorWorkerPool,
    GitAutonomyResult,
    GitStage,
    LinkedWorkItem,
    PRGenerationRequest,
    PRGeneratorConfig,
    PRStage,
)


class RecordingPRExecutor:
    calls: list[tuple[str, str, dict]] = []
    fail_validation: bool = False

    def execute(self, step):
        step_id = step["step_id"]
        tool = step["tool"]
        tool_input = dict(step.get("input", {}))
        type(self).calls.append((step_id, tool, tool_input))

        command = tool_input.get("cmd", "")
        if "pytest" in command and type(self).fail_validation:
            return ExecutionResult(step_id=step_id, success=False, output="tests failed", logs=("fail",))
        return ExecutionResult(step_id=step_id, success=True, output=f"ran {command}", logs=("ok",))


def git_result(*, pushed: bool = True, risk: str = "medium") -> GitAutonomyResult:
    return GitAutonomyResult(
        task_id="feature-login",
        success=pushed,
        stage=GitStage.PUSHED if pushed else GitStage.COMMITTED,
        branch=BranchPlan(
            name="anubis/task/feature-login",
            base_branch=None,
            command="git checkout -B anubis/task/feature-login",
        ),
        diff=DiffAnalysis(
            changed_files=("api/auth.py", "web/Login.tsx"),
            additions=42,
            deletions=7,
            risk=risk,
            summary=f"2 file(s), +42/-7, risk={risk}",
            raw="diff --git a/api/auth.py b/api/auth.py",
        ),
        commits=(
            CommitPlan(
                message="feat(api): add login endpoint",
                paths=("api/auth.py",),
                stage_command="git add -- api/auth.py",
                commit_command="git commit -m 'feat(api): add login endpoint'",
            ),
            CommitPlan(
                message="feat(web): add login page",
                paths=("web/Login.tsx",),
                stage_command="git add -- web/Login.tsx",
                commit_command="git commit -m 'feat(web): add login page'",
            ),
        ),
        push_result={"success": pushed},
    )


class PRGeneratorTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        RecordingPRExecutor.calls = []
        RecordingPRExecutor.fail_validation = False
        self.event_bus = EventBus()

    async def asyncTearDown(self) -> None:
        await self.event_bus.drain()
        self.event_bus.close()

    def generator(self, *, create_remote: bool = True) -> AutonomousPRGenerator:
        return AutonomousPRGenerator(
            executor_pool=ExecutorWorkerPool(
                max_workers=1,
                executor_factory=RecordingPRExecutor,
                event_bus=self.event_bus,
            ),
            event_bus=self.event_bus,
            config=PRGeneratorConfig(create_remote=create_remote),
        )

    async def test_pr_generator_creates_production_ready_pr(self) -> None:
        generator = self.generator()
        events = []
        self.event_bus.subscribe(None, events.append)

        result = await generator.run(
            PRGenerationRequest(
                task_id="feature-login",
                goal="Add login flow for #42 and AUTH-77",
                git_result=git_result(),
                repo_path="/repos/anubis",
                validation_commands=("pytest tests/api tests/web",),
                labels=("autonomous", "feature"),
            )
        )
        await self.event_bus.drain()

        self.assertTrue(result.success)
        self.assertEqual(result.stage, PRStage.CREATED)
        self.assertEqual(result.payload.title, "Add login endpoint")
        self.assertEqual(result.payload.head_branch, "anubis/task/feature-login")
        self.assertEqual(result.payload.base_branch, "main")
        self.assertIn("## Summary", result.payload.body)
        self.assertIn("feat(api): add login endpoint", result.payload.body)
        self.assertIn("api/auth.py", result.payload.body)
        self.assertIn("medium diff risk", result.payload.body)
        self.assertEqual(
            [(item.identifier, item.kind) for item in result.payload.linked_items],
            [("#42", "issue"), ("AUTH-77", "task")],
        )
        commands = [call[2]["cmd"] for call in RecordingPRExecutor.calls]
        self.assertEqual(commands[0], "pytest tests/api tests/web")
        self.assertTrue(commands[1].startswith("gh pr create "))
        self.assertIn("--label autonomous --label feature", commands[1])
        create_input = RecordingPRExecutor.calls[1][2]
        self.assertTrue(create_input["allow_network"])
        self.assertIn(EventType.TASK_STATE_CHANGED, [event.event_type for event in events])

    async def test_validation_failure_blocks_pr_creation(self) -> None:
        RecordingPRExecutor.fail_validation = True
        generator = self.generator()

        result = await generator.run(
            PRGenerationRequest(
                task_id="feature-login",
                goal="Add login flow",
                git_result=git_result(),
                validation_commands=("pytest tests/api",),
            )
        )

        self.assertFalse(result.success)
        self.assertEqual(result.stage, PRStage.FAILED)
        self.assertEqual(result.error, "validation failed before PR creation")
        commands = [call[2]["cmd"] for call in RecordingPRExecutor.calls]
        self.assertEqual(commands, ["pytest tests/api"])

    async def test_pr_payload_can_be_prepared_without_remote_creation(self) -> None:
        generator = self.generator(create_remote=False)

        result = await generator.run(
            PRGenerationRequest(
                task_id="feature-login",
                goal="Add login flow",
                git_result=git_result(risk="low"),
                linked_items=(LinkedWorkItem("#123", "issue"),),
                create_remote=False,
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.stage, PRStage.READY)
        self.assertIsNone(result.creation_result)
        self.assertEqual(result.payload.linked_items[0].identifier, "#123")
        self.assertEqual(RecordingPRExecutor.calls, [])

    async def test_missing_validation_evidence_fails_closed(self) -> None:
        generator = self.generator()

        result = await generator.run(
            PRGenerationRequest(
                task_id="feature-login",
                goal="Add login flow",
                head_branch="anubis/task/feature-login",
            )
        )

        self.assertFalse(result.success)
        self.assertEqual(result.validation.error, "no validation evidence provided")

    async def test_unpushed_git_branch_blocks_pr_creation(self) -> None:
        generator = self.generator()

        result = await generator.run(
            PRGenerationRequest(
                task_id="feature-login",
                goal="Add login flow",
                git_result=git_result(pushed=False),
            )
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "validation failed before PR creation")
        self.assertEqual(RecordingPRExecutor.calls, [])


if __name__ == "__main__":
    unittest.main()
