from __future__ import annotations

import asyncio

from anubis import (
    AgentDescriptor,
    AgentRunResult,
    EventType,
    ExecutionLayer,
    ExecutionPolicy,
    ExecutionStatus,
    Orchestrator,
    RetryPolicy,
    Task,
    TaskStatus,
)
from anubis.events import InMemoryEventBus


async def test_execution_retries_until_success() -> None:
    attempts = 0
    layer = ExecutionLayer(
        policy=ExecutionPolicy(retry=RetryPolicy(max_attempts=3)),
    )

    async def executor(_: Task) -> AgentRunResult:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("not yet")
        return AgentRunResult({"ok": True})

    result = await layer.run(
        task=Task(kind="retry"),
        agent_name="agent",
        executor=executor,
    )

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.attempts == 3
    assert result.result is not None
    assert result.result.output["ok"] is True


async def test_execution_rolls_back_after_final_failure() -> None:
    rolled_back: list[str] = []
    layer = ExecutionLayer(
        policy=ExecutionPolicy(retry=RetryPolicy(max_attempts=2)),
    )

    async def executor(_: Task) -> AgentRunResult:
        raise RuntimeError("boom")

    async def rollback(task: Task, _: AgentRunResult | None, error: BaseException | None) -> None:
        rolled_back.append(f"{task.kind}:{error}")

    result = await layer.run(
        task=Task(kind="danger"),
        agent_name="agent",
        executor=executor,
        rollback=rollback,
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.attempts == 2
    assert result.rollback_attempted is True
    assert result.rollback_succeeded is True
    assert rolled_back == ["danger:boom"]


async def test_execution_timeout_is_isolated_as_failure() -> None:
    layer = ExecutionLayer(
        policy=ExecutionPolicy(
            retry=RetryPolicy(max_attempts=1),
            timeout_seconds=0.01,
            rollback_on_failure=False,
        ),
    )

    async def executor(_: Task) -> AgentRunResult:
        await asyncio.sleep(30)
        return AgentRunResult()

    result = await layer.run(
        task=Task(kind="slow"),
        agent_name="agent",
        executor=executor,
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.rollback_attempted is False


async def test_orchestrator_records_execution_retry_and_rollback_metadata() -> None:
    bus = InMemoryEventBus()
    orchestrator = Orchestrator(
        event_bus=bus,
        execution_layer=ExecutionLayer(
            policy=ExecutionPolicy(retry=RetryPolicy(max_attempts=2)),
            event_bus=bus,
        ),
    )
    rolled_back: list[str] = []

    async def handler(_: Task) -> AgentRunResult:
        raise RuntimeError("agent failed")

    async def rollback(task: Task, _: AgentRunResult | None, __: BaseException | None) -> None:
        rolled_back.append(task.id)

    await orchestrator.register_agent(
        AgentDescriptor(name="agent", capabilities=frozenset({"x"})),
        handler,
        rollback_handler=rollback,
    )

    task_id = await orchestrator.submit(Task(kind="x", required_capabilities=frozenset({"x"})))
    result = await orchestrator.wait(task_id)

    assert result.status == TaskStatus.FAILED
    assert result.output["attempts"] == 2
    assert result.output["rollback_attempted"] is True
    assert result.output["rollback_succeeded"] is True
    assert rolled_back == [task_id]
    assert EventType.EXECUTION_RETRY_SCHEDULED in [event.type for event in bus.events]
    assert EventType.EXECUTION_ROLLBACK_SUCCEEDED in [event.type for event in bus.events]

