from __future__ import annotations

import asyncio

from anubis.agents import AgentHandler, AgentRegistry
from anubis.events import EventBus, InMemoryEventBus
from anubis.execution import ExecutionLayer, ExecutionStatus, RollbackHandler
from anubis.state import InMemoryStateStore, StateStore, TaskRecord
from anubis.types import (
    AgentDescriptor,
    AgentRunResult,
    AgentStatus,
    Event,
    EventType,
    Task,
    TaskResult,
    TaskStatus,
)


class Orchestrator:
    """Central task orchestrator.

    The orchestrator owns lifecycle transitions and routes tasks to registered
    agents. It deliberately depends on interfaces for state and events so the
    in-memory defaults can be replaced by durable services.
    """

    def __init__(
        self,
        *,
        state_store: StateStore | None = None,
        event_bus: EventBus | None = None,
        agent_registry: AgentRegistry | None = None,
        execution_layer: ExecutionLayer | None = None,
    ) -> None:
        self.state_store = state_store or InMemoryStateStore()
        self.event_bus = event_bus or InMemoryEventBus()
        self.agent_registry = agent_registry or AgentRegistry()
        self.execution_layer = execution_layer or ExecutionLayer(event_bus=self.event_bus)
        self._running: dict[str, asyncio.Task[TaskResult]] = {}
        self._lock = asyncio.Lock()

    async def register_agent(
        self,
        descriptor: AgentDescriptor,
        handler: AgentHandler,
        rollback_handler: RollbackHandler | None = None,
    ) -> None:
        await self.agent_registry.register(descriptor, handler, rollback_handler)
        await self.state_store.put_agent(descriptor.name, AgentStatus.IDLE)
        await self._publish(
            EventType.AGENT_REGISTERED,
            producer="orchestrator",
            agent_name=descriptor.name,
            payload={
                "name": descriptor.name,
                "capabilities": sorted(descriptor.capabilities),
                "max_concurrency": descriptor.max_concurrency,
                "version": descriptor.version,
            },
        )

    async def submit(self, task: Task) -> str:
        await self.state_store.put_task(task)
        await self._publish_task(EventType.TASK_SUBMITTED, task, {"status": TaskStatus.PENDING})
        await self._route(task)
        return task.id

    async def wait(self, task_id: str) -> TaskResult:
        async with self._lock:
            running = self._running.get(task_id)
        if running is None:
            record = await self.state_store.get_task(task_id)
            if record.result is not None:
                return record.result
            raise KeyError(f"task is not running: {task_id}")
        return await running

    async def cancel(self, task_id: str) -> None:
        async with self._lock:
            running = self._running.get(task_id)
        if running is None:
            raise KeyError(f"task is not running: {task_id}")
        running.cancel()
        try:
            await running
        except asyncio.CancelledError:
            pass

    async def task_state(self, task_id: str) -> TaskRecord:
        return await self.state_store.get_task(task_id)

    async def shutdown(self) -> None:
        async with self._lock:
            running = tuple(self._running.values())
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)

    async def _route(self, task: Task) -> None:
        try:
            agent = await self.agent_registry.select(task)
        except LookupError as exc:
            result = TaskResult(task_id=task.id, status=TaskStatus.FAILED, error=str(exc))
            await self.state_store.update_task(task.id, TaskStatus.FAILED, result=result, error=str(exc))
            await self._publish_task(
                EventType.TASK_FAILED,
                task,
                {"status": TaskStatus.FAILED, "error": str(exc)},
            )
            return

        await self.state_store.update_task(
            task.id,
            TaskStatus.ROUTED,
            agent_name=agent.descriptor.name,
        )
        await self._publish_task(
            EventType.TASK_ROUTED,
            task,
            {"status": TaskStatus.ROUTED, "agent_name": agent.descriptor.name},
            agent_name=agent.descriptor.name,
        )

        running = asyncio.create_task(
            self._run_agent_task(agent.descriptor.name, agent.handler, task),
            name=f"anubis:{task.id}",
        )
        async with self._lock:
            self._running[task.id] = running

    async def _run_agent_task(
        self,
        agent_name: str,
        handler: AgentHandler,
        task: Task,
    ) -> TaskResult:
        active_tasks = await self.agent_registry.mark_started(agent_name, task.id)
        await self.state_store.update_agent(
            agent_name,
            AgentStatus.RUNNING,
            active_tasks=active_tasks,
        )
        await self.state_store.update_task(task.id, TaskStatus.RUNNING, agent_name=agent_name)
        await self._publish_task(
            EventType.AGENT_SPAWNED,
            task,
            {"agent_name": agent_name, "active_tasks": sorted(active_tasks)},
            agent_name=agent_name,
        )
        await self._publish_task(
            EventType.TASK_STARTED,
            task,
            {"status": TaskStatus.RUNNING},
            agent_name=agent_name,
        )

        try:
            execution = await self.execution_layer.run(
                task=task,
                agent_name=agent_name,
                executor=handler,
                rollback=(await self.agent_registry.get(agent_name)).rollback_handler,
            )
            if execution.status != ExecutionStatus.SUCCEEDED or execution.result is None:
                result = TaskResult(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    error=execution.error or "execution failed",
                    output={
                        "attempts": execution.attempts,
                        "rollback_attempted": execution.rollback_attempted,
                        "rollback_succeeded": execution.rollback_succeeded,
                    },
                )
                await self.state_store.update_task(
                    task.id,
                    TaskStatus.FAILED,
                    agent_name=agent_name,
                    result=result,
                    error=result.error,
                )
                await self._publish_task(
                    EventType.TASK_FAILED,
                    task,
                    {
                        "status": TaskStatus.FAILED,
                        "error": result.error,
                        "attempts": execution.attempts,
                        "rollback_attempted": execution.rollback_attempted,
                        "rollback_succeeded": execution.rollback_succeeded,
                    },
                    agent_name=agent_name,
                )
                return result
            run_result = execution.result
            result = TaskResult(
                task_id=task.id,
                status=TaskStatus.SUCCEEDED,
                output=run_result.output,
            )
            await self.state_store.update_task(
                task.id,
                TaskStatus.SUCCEEDED,
                agent_name=agent_name,
                result=result,
            )
            await self._publish_task(
                EventType.TASK_SUCCEEDED,
                task,
                {"status": TaskStatus.SUCCEEDED, "output": dict(result.output)},
                agent_name=agent_name,
            )
            return result
        except asyncio.CancelledError:
            result = TaskResult(task_id=task.id, status=TaskStatus.CANCELLED, error="cancelled")
            await self.state_store.update_task(
                task.id,
                TaskStatus.CANCELLED,
                agent_name=agent_name,
                result=result,
                error="cancelled",
            )
            await self._publish_task(
                EventType.TASK_CANCELLED,
                task,
                {"status": TaskStatus.CANCELLED},
                agent_name=agent_name,
            )
            raise
        except Exception as exc:
            result = TaskResult(task_id=task.id, status=TaskStatus.FAILED, error=str(exc))
            await self.state_store.update_task(
                task.id,
                TaskStatus.FAILED,
                agent_name=agent_name,
                result=result,
                error=str(exc),
            )
            await self._publish_task(
                EventType.TASK_FAILED,
                task,
                {"status": TaskStatus.FAILED, "error": str(exc)},
                agent_name=agent_name,
            )
            return result
        finally:
            active_tasks = await self.agent_registry.mark_finished(agent_name, task.id)
            next_status = AgentStatus.RUNNING if active_tasks else AgentStatus.IDLE
            await self.state_store.update_agent(
                agent_name,
                next_status,
                active_tasks=active_tasks,
            )
            await self._publish_task(
                EventType.AGENT_STOPPED,
                task,
                {"agent_name": agent_name, "active_tasks": sorted(active_tasks)},
                agent_name=agent_name,
            )
            async with self._lock:
                self._running.pop(task.id, None)

    async def _publish_task(
        self,
        event_type: EventType,
        task: Task,
        payload: dict[str, object],
        *,
        agent_name: str | None = None,
    ) -> None:
        await self._publish(
            event_type,
            producer="orchestrator",
            correlation_id=task.correlation_id,
            task_id=task.id,
            agent_name=agent_name,
            payload=payload,
        )

    async def _publish(
        self,
        event_type: EventType,
        *,
        producer: str,
        payload: dict[str, object],
        correlation_id: str | None = None,
        task_id: str | None = None,
        agent_name: str | None = None,
    ) -> None:
        await self.event_bus.publish(
            Event(
                type=event_type,
                producer=producer,
                payload=payload,
                correlation_id=correlation_id,
                task_id=task_id,
                agent_name=agent_name,
            )
        )
