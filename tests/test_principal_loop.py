from anubis.api_body.stimulus_input import StimulusInput
from anubis.core_life.living_loop import PrincipalLoop
from anubis.events import InMemoryEventBus
from anubis.orchestrator import Orchestrator
from anubis.types import AgentDescriptor, AgentRunResult, EventType, Task, TaskStatus


async def test_principal_loop_runs_full_stimulus_to_reflection_cycle():
    bus = InMemoryEventBus()
    orchestrator = Orchestrator(event_bus=bus)

    async def handler(task: Task) -> AgentRunResult:
        return AgentRunResult(output={"handled": task.payload["objective"]})

    await orchestrator.register_agent(
        AgentDescriptor(
            name="watcher",
            capabilities=frozenset(
                {
                    "telemetry.read",
                    "reason.plan",
                    "policy.evaluate",
                }
            ),
        ),
        handler,
    )

    loop = PrincipalLoop(orchestrator=orchestrator, event_bus=bus)
    result = await loop.run(StimulusInput("suspicious login spike", source="sensor"))

    assert result.succeeded
    assert result.goal.objective == "suspicious login spike"
    assert result.task.payload["objective"] == "suspicious login spike"
    assert result.task_result.status == TaskStatus.SUCCEEDED
    assert result.task_result.output["handled"] == "suspicious login spike"
    assert result.memory_write.record is not None
    assert "suspicious login spike" in result.memory_write.record.content
    assert result.reflection.event_count >= 1

    event_types = [event.type for event in bus.events]
    assert EventType.LIFE_LOOP_STARTED in event_types
    assert EventType.TASK_SUCCEEDED in event_types
    assert EventType.SELF_PERFORMANCE_ANALYZED in event_types
    assert EventType.LIFE_LOOP_COMPLETED in event_types


async def test_principal_loop_keeps_patch_application_disabled_by_default():
    bus = InMemoryEventBus()
    orchestrator = Orchestrator(event_bus=bus)

    async def handler(task: Task) -> AgentRunResult:
        return AgentRunResult(output={"ok": True})

    await orchestrator.register_agent(
        AgentDescriptor(
            name="executor",
            capabilities=frozenset({"telemetry.read", "reason.plan", "policy.evaluate"}),
        ),
        handler,
    )

    loop = PrincipalLoop(
        orchestrator=orchestrator,
        event_bus=bus,
        evolution_paths=("src/anubis/types.py",),
    )
    result = await loop.run("inspect architecture health")

    assert all(patch.applied is False for patch in result.patch_results)
    assert all(patch.requires_human_approval for patch in result.patch_results)
    assert result.task_result.status == TaskStatus.SUCCEEDED
