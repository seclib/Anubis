import unittest

from anubis.distributed import (
    ContinuousImprovementEngine,
    EventBus,
    EventType,
    ExecutionResult,
    ExecutorWorkerPool,
    ImprovementEngineConfig,
    ImprovementExecutionResult,
    ImprovementKind,
    ImprovementRisk,
    ImprovementStage,
    MultiRepoOrchestrator,
    RepoRegistry,
    RepoRole,
    RepositoryMetadata,
)


class RecordingImprovementExecutor:
    calls: list[tuple[str, str, dict]] = []

    def execute(self, step):
        step_id = step["step_id"]
        tool = step["tool"]
        tool_input = dict(step.get("input", {}))
        type(self).calls.append((step_id, tool, tool_input))
        cwd = tool_input.get("cwd", "")
        if cwd.endswith("/api"):
            output = "api/auth.py has missing tests and coverage gap"
        elif cwd.endswith("/worker"):
            output = "worker/jobs.py has slow database critical path and duplicate logic"
        else:
            output = "docs are healthy"
        return ExecutionResult(step_id=step_id, success=True, output=output, logs=("scan",))


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
            RepositoryMetadata(
                repo_id="worker",
                name="anubis-worker",
                path="/repos/worker",
                language="python",
                structure=("worker/jobs", "tests"),
                role=RepoRole.SERVICE,
                tags=("jobs",),
                metadata={"test_command": "pytest tests/worker"},
            ),
        )
    )


class ImprovementEngineTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        RecordingImprovementExecutor.calls = []
        self.event_bus = EventBus()
        self.executed = []

    async def asyncTearDown(self) -> None:
        await self.event_bus.drain()
        self.event_bus.close()

    def engine(self, *, allow_high_risk: bool = False, max_tasks: int = 3) -> ContinuousImprovementEngine:
        async def pipeline(task):
            self.executed.append(task)
            return ImprovementExecutionResult(task=task, success=True)

        return ContinuousImprovementEngine(
            repo_orchestrator=MultiRepoOrchestrator(registry=registry()),
            executor_pool=ExecutorWorkerPool(
                max_workers=2,
                executor_factory=RecordingImprovementExecutor,
                event_bus=self.event_bus,
            ),
            event_bus=self.event_bus,
            pipeline_runner=pipeline,
            config=ImprovementEngineConfig(
                max_tasks_per_cycle=max_tasks,
                allow_high_risk=allow_high_risk,
                default_test_command="pytest",
            ),
        )

    async def test_improvement_engine_scans_detects_generates_and_executes_safe_tasks(self) -> None:
        engine = self.engine()
        events = []
        self.event_bus.subscribe(None, events.append)

        result = await engine.run_cycle("cycle-001")
        await self.event_bus.drain()

        self.assertTrue(result.success)
        self.assertEqual(result.stage, ImprovementStage.COMPLETED)
        self.assertEqual({scan.repo_id for scan in result.scans}, {"api", "worker"})
        self.assertTrue(any(candidate.kind == ImprovementKind.MISSING_TESTS for candidate in result.candidates))
        self.assertTrue(all(task.candidate.risk != ImprovementRisk.HIGH for task in result.tasks))
        self.assertEqual(len(self.executed), len(result.tasks))
        api_task = next(task for task in result.tasks if task.repo.repo_id == "api")
        self.assertEqual(api_task.test_commands, ("pytest tests/api",))
        self.assertIn("preserve production behavior", api_task.requirement)
        self.assertIn(EventType.TASK_STATE_CHANGED, [event.event_type for event in events])

    async def test_improvement_engine_skips_high_risk_by_default(self) -> None:
        engine = self.engine(allow_high_risk=False)

        result = await engine.run_cycle("cycle-002")

        high_risk_candidates = [candidate for candidate in result.candidates if candidate.risk == ImprovementRisk.HIGH]
        self.assertTrue(high_risk_candidates)
        self.assertNotIn(
            ImprovementRisk.HIGH,
            {task.candidate.risk for task in result.tasks},
        )

    async def test_improvement_engine_can_allow_high_risk_explicitly(self) -> None:
        engine = self.engine(allow_high_risk=True, max_tasks=10)

        result = await engine.run_cycle("cycle-003")

        self.assertIn(
            ImprovementRisk.HIGH,
            {task.candidate.risk for task in result.tasks},
        )

    async def test_improvement_engine_reports_pipeline_failure(self) -> None:
        async def failing_pipeline(task):
            self.executed.append(task)
            return ImprovementExecutionResult(task=task, success=False, error="pipeline failed")

        engine = ContinuousImprovementEngine(
            repo_orchestrator=MultiRepoOrchestrator(registry=registry()),
            executor_pool=ExecutorWorkerPool(
                max_workers=2,
                executor_factory=RecordingImprovementExecutor,
                event_bus=self.event_bus,
            ),
            event_bus=self.event_bus,
            pipeline_runner=failing_pipeline,
            config=ImprovementEngineConfig(max_tasks_per_cycle=1),
        )

        result = await engine.run_cycle("cycle-004")

        self.assertFalse(result.success)
        self.assertEqual(result.stage, ImprovementStage.FAILED)
        self.assertEqual(result.executions[0].error, "pipeline failed")


if __name__ == "__main__":
    unittest.main()
