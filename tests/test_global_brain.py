import unittest

from anubis.distributed import (
    AgentRegistration,
    AgentRegistry,
    AgentType,
    AutonomousPipelineCycleResult,
    AutonomousPipelineStage,
    BrainTask,
    BrainTaskKind,
    BrainTaskRisk,
    EventBus,
    EventType,
    GlobalBrain,
    GlobalBrainConfig,
    GlobalBrainStage,
    MultiRepoOrchestrator,
    RepoRegistry,
    RepoRole,
    RepositoryMetadata,
)


def repos() -> tuple[RepositoryMetadata, ...]:
    return (
        RepositoryMetadata(
            repo_id="api",
            name="anubis-api",
            path="/repos/api",
            language="python",
            structure=("backend/routes", "services/auth"),
            role=RepoRole.BACKEND,
            tags=("auth", "fastapi"),
        ),
        RepositoryMetadata(
            repo_id="web",
            name="anubis-web",
            path="/repos/web",
            language="typescript",
            structure=("src/components", "src/api-client"),
            role=RepoRole.FRONTEND,
            tags=("react", "ui"),
            dependencies=("api",),
        ),
    )


def registry() -> AgentRegistry:
    agents = AgentRegistry()
    agents.register(AgentRegistration(agent_id="planner-1", agent_type=AgentType.PLANNER, max_concurrent=1))
    agents.register(AgentRegistration(agent_id="executor-1", agent_type=AgentType.EXECUTOR, max_concurrent=2))
    agents.register(AgentRegistration(agent_id="reviewer-1", agent_type=AgentType.REVIEWER, max_concurrent=1))
    return agents


def tasks() -> tuple[BrainTask, ...]:
    return (
        BrainTask(
            task_id="refactor-001",
            title="Refactor component names",
            description="Clean frontend naming",
            kind=BrainTaskKind.REFACTOR,
            priority=2,
            risk=BrainTaskRisk.LOW,
            repo_hints=("web",),
        ),
        BrainTask(
            task_id="security-001",
            title="Fix auth token leak",
            description="Patch backend auth security issue",
            kind=BrainTaskKind.SECURITY,
            priority=5,
            risk=BrainTaskRisk.MEDIUM,
            repo_hints=("api",),
        ),
        BrainTask(
            task_id="risky-001",
            title="Rewrite persistence layer",
            description="High risk database rewrite",
            kind=BrainTaskKind.FEATURE,
            priority=10,
            risk=BrainTaskRisk.HIGH,
        ),
    )


class FakePipeline:
    def __init__(self, success=True):
        self.success = success
        self.calls = []

    async def run_once(self, cycle_id=None):
        self.calls.append(cycle_id)
        return AutonomousPipelineCycleResult(
            cycle_id=cycle_id,
            success=self.success,
            stage=AutonomousPipelineStage.COMPLETED if self.success else AutonomousPipelineStage.FAILED,
        )


class GlobalBrainTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.event_bus = EventBus()

    async def asyncTearDown(self) -> None:
        await self.event_bus.drain()
        self.event_bus.close()

    def brain(self, *, agents=None, pipeline=None, run_pipeline=False, max_parallel=2) -> GlobalBrain:
        return GlobalBrain(
            repo_orchestrator=MultiRepoOrchestrator(registry=RepoRegistry(repos())),
            agent_registry=agents or registry(),
            autonomous_pipeline=pipeline or FakePipeline(),
            event_bus=self.event_bus,
            config=GlobalBrainConfig(run_pipeline=run_pipeline, max_parallel_tasks=max_parallel),
        )

    async def test_global_brain_prioritizes_safe_high_value_tasks(self) -> None:
        brain = self.brain()

        prioritized = brain.prioritize_tasks(tasks())

        self.assertEqual([item.task.task_id for item in prioritized], ["security-001", "refactor-001"])
        self.assertGreater(prioritized[0].score, prioritized[1].score)
        self.assertNotIn("risky-001", [item.task.task_id for item in prioritized])

    async def test_global_brain_allocates_agent_capacity_without_overbooking(self) -> None:
        brain = self.brain(max_parallel=3)
        prioritized = brain.prioritize_tasks(tasks()[:2])

        allocations = brain.allocate_resources(prioritized)

        self.assertFalse(allocations[0].saturated)
        self.assertEqual(allocations[0].agent_assignments["planner"], ("planner-1",))
        self.assertTrue(allocations[1].saturated)
        self.assertNotIn("planner", allocations[1].agent_assignments)

    async def test_global_brain_coordinates_cross_repo_tasks(self) -> None:
        brain = self.brain()
        task = BrainTask(
            task_id="fullstack-001",
            title="Build fullstack login",
            description="React frontend and FastAPI backend integration",
            kind=BrainTaskKind.FEATURE,
            priority=3,
            risk=BrainTaskRisk.LOW,
            repo_hints=("web", "api"),
        )

        plans = brain.coordinate_repositories(brain.prioritize_tasks((task,)))

        self.assertTrue(plans[0].plan.cross_repo)
        self.assertEqual([route.repo_id for route in plans[0].plan.routes], ["api", "web"])

    async def test_global_brain_schedules_and_runs_pipeline_when_capacity_exists(self) -> None:
        pipeline = FakePipeline(success=True)
        brain = self.brain(pipeline=pipeline, run_pipeline=True)
        events = []
        self.event_bus.subscribe(None, events.append)

        result = await brain.run_cycle("brain-001", tasks()[:2])
        await self.event_bus.drain()

        self.assertTrue(result.success)
        self.assertEqual(result.stage, GlobalBrainStage.COMPLETED)
        self.assertEqual(pipeline.calls, ["brain-001"])
        self.assertEqual([item.task.task_id for item in result.schedule.scheduled_tasks], ["security-001"])
        self.assertIn(EventType.TASK_STATE_CHANGED, [event.event_type for event in events])

    async def test_global_brain_does_not_run_pipeline_without_required_capacity(self) -> None:
        pipeline = FakePipeline(success=True)
        brain = self.brain(agents=AgentRegistry(), pipeline=pipeline, run_pipeline=True)

        result = await brain.run_cycle("brain-002", tasks()[:1])

        self.assertTrue(result.success)
        self.assertEqual(result.stage, GlobalBrainStage.IDLE)
        self.assertEqual(result.schedule.scheduled_tasks, ())
        self.assertEqual(pipeline.calls, [])

    async def test_global_brain_reports_pipeline_failure(self) -> None:
        pipeline = FakePipeline(success=False)
        brain = self.brain(pipeline=pipeline, run_pipeline=True)

        result = await brain.run_cycle("brain-003", tasks()[:1])

        self.assertFalse(result.success)
        self.assertEqual(result.stage, GlobalBrainStage.FAILED)
        self.assertEqual(result.error, "autonomous pipeline failed")


if __name__ == "__main__":
    unittest.main()
