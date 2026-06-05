from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from anubis.events import EventBus
from anubis.types import AgentRunResult, Event, EventType, Task

TaskExecutor = Callable[[Task], Awaitable[AgentRunResult]]
RollbackHandler = Callable[[Task, AgentRunResult | None, BaseException | None], Awaitable[None]]


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0
    retryable_exceptions: tuple[type[BaseException], ...] = (Exception,)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be non-negative")

    def can_retry(self, exc: BaseException, attempt: int) -> bool:
        return attempt < self.max_attempts and isinstance(exc, self.retryable_exceptions)


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_seconds: float | None = None
    rollback_on_failure: bool = True
    rollback_timeout_seconds: float | None = 10

    def __post_init__(self) -> None:
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.rollback_timeout_seconds is not None and self.rollback_timeout_seconds <= 0:
            raise ValueError("rollback_timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: ExecutionStatus
    attempts: int
    result: AgentRunResult | None = None
    error: str | None = None
    rollback_attempted: bool = False
    rollback_succeeded: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class ExecutionLayer:
    """Runs agent tasks with bounded failure, retry, timeout, and rollback semantics."""

    def __init__(
        self,
        *,
        policy: ExecutionPolicy | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.policy = policy or ExecutionPolicy()
        self.event_bus = event_bus

    async def run(
        self,
        *,
        task: Task,
        agent_name: str,
        executor: TaskExecutor,
        rollback: RollbackHandler | None = None,
        policy: ExecutionPolicy | None = None,
    ) -> ExecutionResult:
        active_policy = policy or self.policy
        last_error: BaseException | None = None
        last_result: AgentRunResult | None = None

        for attempt in range(1, active_policy.retry.max_attempts + 1):
            await self._publish(
                EventType.EXECUTION_ATTEMPT_STARTED,
                task,
                agent_name,
                {"attempt": attempt, "max_attempts": active_policy.retry.max_attempts},
            )
            try:
                result = await self._run_once(executor, task, active_policy)
                return ExecutionResult(
                    status=ExecutionStatus.SUCCEEDED,
                    attempts=attempt,
                    result=result,
                    metadata={"agent_name": agent_name},
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                await self._publish(
                    EventType.EXECUTION_ATTEMPT_FAILED,
                    task,
                    agent_name,
                    {"attempt": attempt, "error": str(exc), "error_type": type(exc).__name__},
                )
                if active_policy.retry.can_retry(exc, attempt):
                    await self._publish(
                        EventType.EXECUTION_RETRY_SCHEDULED,
                        task,
                        agent_name,
                        {
                            "attempt": attempt + 1,
                            "backoff_seconds": active_policy.retry.backoff_seconds,
                        },
                    )
                    if active_policy.retry.backoff_seconds:
                        await asyncio.sleep(active_policy.retry.backoff_seconds)
                    continue
                break

        rollback_attempted = False
        rollback_succeeded: bool | None = None
        if active_policy.rollback_on_failure and rollback is not None:
            rollback_attempted = True
            rollback_succeeded = await self._rollback(
                task=task,
                agent_name=agent_name,
                rollback=rollback,
                result=last_result,
                error=last_error,
                timeout_seconds=active_policy.rollback_timeout_seconds,
            )

        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            attempts=active_policy.retry.max_attempts,
            error=str(last_error) if last_error is not None else "execution failed",
            rollback_attempted=rollback_attempted,
            rollback_succeeded=rollback_succeeded,
            metadata={"agent_name": agent_name},
        )

    async def _run_once(
        self,
        executor: TaskExecutor,
        task: Task,
        policy: ExecutionPolicy,
    ) -> AgentRunResult:
        if policy.timeout_seconds is None:
            result = await executor(task)
        else:
            result = await asyncio.wait_for(executor(task), timeout=policy.timeout_seconds)
        if not isinstance(result, AgentRunResult):
            raise TypeError("agent handler must return AgentRunResult")
        return result

    async def _rollback(
        self,
        *,
        task: Task,
        agent_name: str,
        rollback: RollbackHandler,
        result: AgentRunResult | None,
        error: BaseException | None,
        timeout_seconds: float | None,
    ) -> bool:
        await self._publish(
            EventType.EXECUTION_ROLLBACK_STARTED,
            task,
            agent_name,
            {"error": str(error) if error else None},
        )
        try:
            if timeout_seconds is None:
                await rollback(task, result, error)
            else:
                await asyncio.wait_for(rollback(task, result, error), timeout=timeout_seconds)
        except Exception as rollback_error:
            await self._publish(
                EventType.EXECUTION_ROLLBACK_FAILED,
                task,
                agent_name,
                {
                    "error": str(rollback_error),
                    "error_type": type(rollback_error).__name__,
                },
            )
            return False

        await self._publish(EventType.EXECUTION_ROLLBACK_SUCCEEDED, task, agent_name, {})
        return True

    async def _publish(
        self,
        event_type: EventType,
        task: Task,
        agent_name: str,
        payload: Mapping[str, Any],
    ) -> None:
        if self.event_bus is None:
            return
        await self.event_bus.publish(
            Event(
                type=event_type,
                producer="execution",
                payload=payload,
                correlation_id=task.correlation_id,
                task_id=task.id,
                agent_name=agent_name,
            )
        )
