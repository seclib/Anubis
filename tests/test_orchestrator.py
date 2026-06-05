from __future__ import annotations

import asyncio

import pytest

from anubis import AgentDescriptor, AgentRunResult, EventType, Orchestrator, Task, TaskStatus
from anubis.events import InMemoryEventBus


async def test_routes_task_to_capable_agent_and_tracks_success() -> None:
    bus = InMemoryEventBus()
    orchestrator = Orchestrator(event_bus=bus)

    async def handler(task: Task) -> AgentRunResult:
        return AgentRunResult({"handled": task.kind})

    await orchestrator.register_agent(
        AgentDescriptor(name="planner", capabilities=frozenset({"plan"})),
        handler,
    )

    task_id = await orchestrator.submit(Task(kind="investigate", required_capabilities=frozenset({"plan"})))
    result = await orchestrator.wait(task_id)
    record = await orchestrator.task_state(task_id)

    assert result.status == TaskStatus.SUCCEEDED
    assert result.output["handled"] == "investigate"
    assert record.status == TaskStatus.SUCCEEDED
    assert record.agent_name == "planner"
    assert [event.type for event in bus.events] == [
        EventType.AGENT_REGISTERED,
        EventType.TASK_SUBMITTED,
        EventType.TASK_ROUTED,
        EventType.AGENT_SPAWNED,
        EventType.TASK_STARTED,
        EventType.TASK_SUCCEEDED,
        EventType.AGENT_STOPPED,
    ]


async def test_unroutable_task_fails_with_state_record() -> None:
    orchestrator = Orchestrator()
    task_id = await orchestrator.submit(Task(kind="scan", required_capabilities=frozenset({"network"})))
    record = await orchestrator.task_state(task_id)

    assert record.status == TaskStatus.FAILED
    assert record.result is not None
    assert "no available agent" in (record.result.error or "")


async def test_agent_failure_is_captured_as_task_failure() -> None:
    orchestrator = Orchestrator()

    async def handler(_: Task) -> AgentRunResult:
        raise RuntimeError("sensor unavailable")

    await orchestrator.register_agent(
        AgentDescriptor(name="sensor", capabilities=frozenset({"collect"})),
        handler,
    )

    task_id = await orchestrator.submit(Task(kind="collect", required_capabilities=frozenset({"collect"})))
    result = await orchestrator.wait(task_id)
    record = await orchestrator.task_state(task_id)

    assert result.status == TaskStatus.FAILED
    assert result.error == "sensor unavailable"
    assert record.status == TaskStatus.FAILED


async def test_cancels_running_task_and_records_lifecycle() -> None:
    bus = InMemoryEventBus()
    orchestrator = Orchestrator(event_bus=bus)
    started = asyncio.Event()

    async def handler(_: Task) -> AgentRunResult:
        started.set()
        await asyncio.sleep(30)
        return AgentRunResult()

    await orchestrator.register_agent(
        AgentDescriptor(name="slow", capabilities=frozenset({"wait"})),
        handler,
    )

    task_id = await orchestrator.submit(Task(kind="wait", required_capabilities=frozenset({"wait"})))
    await started.wait()
    await orchestrator.cancel(task_id)
    record = await orchestrator.task_state(task_id)

    assert record.status == TaskStatus.CANCELLED
    assert record.result is not None
    assert record.result.status == TaskStatus.CANCELLED
    assert EventType.TASK_CANCELLED in [event.type for event in bus.events]


async def test_rejects_invalid_agent_result_type() -> None:
    orchestrator = Orchestrator()

    async def handler(_: Task):  # type: ignore[no-untyped-def]
        return {"not": "an AgentRunResult"}

    await orchestrator.register_agent(
        AgentDescriptor(name="bad", capabilities=frozenset({"bad"})),
        handler,
    )

    task_id = await orchestrator.submit(Task(kind="bad", required_capabilities=frozenset({"bad"})))
    result = await orchestrator.wait(task_id)

    assert result.status == TaskStatus.FAILED
    assert result.error == "agent handler must return AgentRunResult"


async def test_duplicate_agent_registration_fails() -> None:
    orchestrator = Orchestrator()

    async def handler(_: Task) -> AgentRunResult:
        return AgentRunResult()

    descriptor = AgentDescriptor(name="agent", capabilities=frozenset({"x"}))
    await orchestrator.register_agent(descriptor, handler)

    with pytest.raises(ValueError, match="agent already registered"):
        await orchestrator.register_agent(descriptor, handler)

