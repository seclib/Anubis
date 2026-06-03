import unittest

from anubis.distributed import (
    AutonomousFeatureGenerationEngine,
    EventBus,
    EventType,
    ExecutionResult,
    ExecutorWorkerPool,
    FeatureEngineConfig,
    FeatureFileChange,
    FeatureRequest,
    FeatureStage,
    MultiRepoOrchestrator,
    RepoRegistry,
    RepoRole,
    RepositoryMetadata,
)


def registry() -> RepoRegistry:
    return RepoRegistry(
        (
            RepositoryMetadata(
                repo_id="api",
                name="anubis-api",
                path="/repos/api",
                language="python",
                structure=("backend/routes", "services/auth"),
                role=RepoRole.BACKEND,
                tags=("fastapi", "auth"),
                metadata={"test_command": "pytest tests/api"},
            ),
            RepositoryMetadata(
                repo_id="web",
                name="anubis-web",
                path="/repos/web",
                language="typescript",
                structure=("src/components", "src/app"),
                role=RepoRole.FRONTEND,
                tags=("react", "ui"),
                dependencies=("api",),
                metadata={"test_command": "npm test"},
            ),
        )
    )


class RecordingFeatureExecutor:
    calls: list[tuple[str, str, dict]] = []
    fail_first_test: bool = False
    failed_once: bool = False

    def execute(self, step):
        step_id = step["step_id"]
        tool = step["tool"]
        tool_input = dict(step.get("input", {}))
        type(self).calls.append((step_id, tool, tool_input))

        if tool == "run_command" and type(self).fail_first_test and not type(self).failed_once:
            type(self).failed_once = True
            return ExecutionResult(
                step_id=step_id,
                success=False,
                output=f"failing test for {step_id}",
                logs=("test failed",),
            )

        return ExecutionResult(
            step_id=step_id,
            success=True,
            output=f"{tool} completed for {step_id}",
            logs=("ok",),
        )


class FeatureEngineTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        RecordingFeatureExecutor.calls = []
        RecordingFeatureExecutor.fail_first_test = False
        RecordingFeatureExecutor.failed_once = False
        self.event_bus = EventBus()

    async def asyncTearDown(self) -> None:
        await self.event_bus.drain()
        self.event_bus.close()

    def engine(self, *, max_attempts: int = 3) -> AutonomousFeatureGenerationEngine:
        return AutonomousFeatureGenerationEngine(
            repo_orchestrator=MultiRepoOrchestrator(registry=registry()),
            executor_pool=ExecutorWorkerPool(
                max_workers=3,
                executor_factory=RecordingFeatureExecutor,
                event_bus=self.event_bus,
            ),
            event_bus=self.event_bus,
            config=FeatureEngineConfig(max_attempts=max_attempts),
        )

    async def test_feature_engine_runs_end_to_end_and_prepares_pr_draft(self) -> None:
        engine = self.engine()
        events = []
        self.event_bus.subscribe(None, events.append)

        result = await engine.run(
            FeatureRequest(
                feature_id="feature-login",
                description="build fullstack login feature for React frontend and FastAPI backend",
                file_changes=(
                    FeatureFileChange(repo_id="api", path="/repos/api/auth.py", content="def login(): return True\n"),
                    FeatureFileChange(repo_id="web", path="/repos/web/Login.tsx", content="export const Login = () => null\n"),
                ),
            )
        )
        await self.event_bus.drain()

        self.assertTrue(result.success)
        self.assertEqual(result.stage, FeatureStage.COMPLETED)
        self.assertIsNotNone(result.pr_draft)
        self.assertEqual({route.repo_id for route in result.route_results}, {"api", "web"})
        tools = [tool for _step_id, tool, _input in RecordingFeatureExecutor.calls]
        self.assertIn("search_codebase", tools)
        self.assertIn("write_file", tools)
        self.assertIn("run_command", tools)
        self.assertIn("git_diff", tools)
        self.assertIn("git_commit", tools)
        self.assertIn(EventType.TASK_COMPLETED, [event.event_type for event in events])

    async def test_feature_engine_retries_and_self_fixes_after_test_failure(self) -> None:
        RecordingFeatureExecutor.fail_first_test = True
        engine = self.engine(max_attempts=3)

        result = await engine.run(
            FeatureRequest(
                feature_id="feature-api-auth",
                description="fix FastAPI auth backend endpoint",
                file_changes=(FeatureFileChange(repo_id="api", path="/repos/api/auth.py", content="def auth(): return True\n"),),
            )
        )

        self.assertTrue(result.success)
        api_result = next(route for route in result.route_results if route.repo_id == "api")
        self.assertEqual(api_result.attempts, 2)
        self.assertTrue(any(run.success is False for run in api_result.runs))
        test_calls = [call for call in RecordingFeatureExecutor.calls if call[1] == "run_command"]
        self.assertGreaterEqual(len(test_calls), 2)

    async def test_feature_engine_fails_after_max_self_fix_attempts(self) -> None:
        class AlwaysFailTests(RecordingFeatureExecutor):
            def execute(self, step):
                type(self).calls.append((step["step_id"], step["tool"], dict(step.get("input", {}))))
                if step["tool"] == "run_command":
                    return ExecutionResult(step_id=step["step_id"], success=False, output="tests failed", logs=("fail",))
                return ExecutionResult(step_id=step["step_id"], success=True, output=f"ok {step['step_id']}", logs=("ok",))

        engine = AutonomousFeatureGenerationEngine(
            repo_orchestrator=MultiRepoOrchestrator(registry=registry()),
            executor_pool=ExecutorWorkerPool(max_workers=2, executor_factory=AlwaysFailTests, event_bus=self.event_bus),
            event_bus=self.event_bus,
            config=FeatureEngineConfig(max_attempts=2),
        )

        result = await engine.run(
            FeatureRequest(
                feature_id="feature-bad-tests",
                description="fix FastAPI auth backend endpoint",
                file_changes=(FeatureFileChange(repo_id="api", path="/repos/api/auth.py", content="def auth(): return True\n"),),
            )
        )

        self.assertFalse(result.success)
        self.assertEqual(result.stage, FeatureStage.FAILED)
        self.assertEqual(result.error, "one or more repository routes failed")


if __name__ == "__main__":
    unittest.main()
