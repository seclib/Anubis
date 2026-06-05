from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from anubis.api_body.stimulus_input import StimulusInput
from anubis.life_cycle.boot_sequence import AnubisRuntime, build_runtime
from anubis.types import TaskStatus, utcnow


class RequestStatus(StrEnum):
    ACCEPTED = "accepted"
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class StructuredLog:
    sequence: int
    level: str
    action: str
    request_id: str
    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    timestamp: object = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": str(self.timestamp),
            "level": self.level,
            "action": self.action,
            "request_id": self.request_id,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class RequestRecord:
    request_id: str
    input_text: str
    source: str
    status: RequestStatus
    plan_id: str | None = None
    task_ids: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: object = field(default_factory=utcnow)
    updated_at: object = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_ids", tuple(self.task_ids))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    request_id: str
    status: RequestStatus
    goal: str | None
    plan_id: str | None
    plan_status: str | None
    final_task_status: str | None
    task_ids: tuple[str, ...]
    output: Mapping[str, Any] = field(default_factory=dict)
    memory_record_id: str | None = None
    patch_proposals: int = 0
    event_count: int = 0
    error: str | None = None
    logs: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_ids", tuple(self.task_ids))
        object.__setattr__(self, "output", MappingProxyType(dict(self.output)))
        object.__setattr__(
            self,
            "logs",
            tuple(MappingProxyType(dict(log)) for log in self.logs),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status.value,
            "goal": self.goal,
            "plan_id": self.plan_id,
            "plan_status": self.plan_status,
            "final_task_status": self.final_task_status,
            "task_ids": self.task_ids,
            "output": dict(self.output),
            "memory_record_id": self.memory_record_id,
            "patch_proposals": self.patch_proposals,
            "event_count": self.event_count,
            "error": self.error,
            "logs": tuple(dict(log) for log in self.logs),
        }


class Orchestrator:
    """Production control plane for ANUBIS user-input orchestration.

    This layer is intentionally deterministic and side-effect constrained:
    it accepts user input, delegates planning/execution to the sandboxed ANUBIS
    runtime, stores request state, and emits structured in-memory logs. It does
    not execute arbitrary code, deploy changes, or modify source files.
    """

    def __init__(self, runtime: AnubisRuntime) -> None:
        self.runtime = runtime
        self._requests: dict[str, RequestRecord] = {}
        self._logs: list[StructuredLog] = []
        self._next_request = 1
        self._next_log = 1

    @classmethod
    async def create(cls, *, evolution_enabled: bool = False) -> "Orchestrator":
        runtime = await build_runtime(evolution_enabled=evolution_enabled)
        return cls(runtime)

    @property
    def request_state(self) -> tuple[RequestRecord, ...]:
        return tuple(self._requests[key] for key in sorted(self._requests))

    @property
    def logs(self) -> tuple[StructuredLog, ...]:
        return tuple(self._logs)

    async def receive_user_input(
        self,
        text: str,
        *,
        source: str = "operator",
        context: Mapping[str, Any] | None = None,
    ) -> OrchestrationResult:
        request_id = self._allocate_request_id()
        normalized_text = text.strip()
        if not normalized_text:
            record = self._put_record(
                RequestRecord(
                    request_id=request_id,
                    input_text=text,
                    source=source,
                    status=RequestStatus.FAILED,
                    error="input text is empty",
                )
            )
            self._log("error", "input.rejected", request_id, "Rejected empty input.")
            return self._error_result(record)

        self._put_record(
            RequestRecord(
                request_id=request_id,
                input_text=normalized_text,
                source=source,
                status=RequestStatus.ACCEPTED,
                metadata={"context": dict(context or {})},
            )
        )
        self._log(
            "info",
            "input.accepted",
            request_id,
            "Accepted user input for deterministic orchestration.",
            source=source,
        )

        try:
            self._transition(request_id, RequestStatus.PLANNED, "Routing input to planner.")
            self._transition(
                request_id,
                RequestStatus.RUNNING,
                "Planner produced execution-ready graph; dispatching sandboxed tasks.",
            )
            result = await self.runtime.cognitive_loop.run(
                StimulusInput(normalized_text, source=source),
                context={"request_id": request_id, **dict(context or {})},
            )
            task_ids = tuple(step_result.task_id for step_result in result.step_results)
            status = (
                RequestStatus.SUCCEEDED
                if result.task_result.status == TaskStatus.SUCCEEDED
                else RequestStatus.FAILED
            )
            self._put_record(
                RequestRecord(
                    request_id=request_id,
                    input_text=normalized_text,
                    source=source,
                    status=status,
                    plan_id=result.plan.id if result.plan else None,
                    task_ids=task_ids,
                    error=result.task_result.error,
                    metadata={
                        "goal_id": result.goal.id,
                        "patch_proposals": len(result.upgrade_proposals),
                    },
                    created_at=self._requests[request_id].created_at,
                )
            )
            self._log(
                "info",
                "execution.completed",
                request_id,
                "Completed orchestration cycle.",
                plan_id=result.plan.id if result.plan else None,
                task_ids=task_ids,
                final_status=result.task_result.status.value,
            )
            return OrchestrationResult(
                request_id=request_id,
                status=status,
                goal=result.goal.objective,
                plan_id=result.plan.id if result.plan else None,
                plan_status=result.plan.status.value if result.plan else None,
                final_task_status=result.task_result.status.value,
                task_ids=task_ids,
                output=dict(result.task_result.output),
                memory_record_id=(
                    result.memory_write.record.id if result.memory_write.record else None
                ),
                patch_proposals=len(result.upgrade_proposals),
                event_count=len(self.runtime.event_bus.events),
                error=result.task_result.error,
                logs=self._logs_for(request_id),
            )
        except Exception as exc:
            self._put_record(
                RequestRecord(
                    request_id=request_id,
                    input_text=normalized_text,
                    source=source,
                    status=RequestStatus.FAILED,
                    error=str(exc),
                    created_at=self._requests[request_id].created_at,
                )
            )
            self._log(
                "error",
                "execution.failed",
                request_id,
                "Orchestration failed with structured error.",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return self._error_result(self._requests[request_id])

    async def handle_input(
        self,
        text: str,
        *,
        source: str = "operator",
        context: Mapping[str, Any] | None = None,
    ) -> OrchestrationResult:
        return await self.receive_user_input(text, source=source, context=context)

    def _allocate_request_id(self) -> str:
        request_id = f"request_{self._next_request:06d}"
        self._next_request += 1
        return request_id

    def _put_record(self, record: RequestRecord) -> RequestRecord:
        self._requests[record.request_id] = RequestRecord(
            request_id=record.request_id,
            input_text=record.input_text,
            source=record.source,
            status=record.status,
            plan_id=record.plan_id,
            task_ids=record.task_ids,
            error=record.error,
            metadata=record.metadata,
            created_at=record.created_at,
            updated_at=utcnow(),
        )
        return self._requests[record.request_id]

    def _transition(self, request_id: str, status: RequestStatus, message: str) -> None:
        current = self._requests[request_id]
        self._put_record(
            RequestRecord(
                request_id=current.request_id,
                input_text=current.input_text,
                source=current.source,
                status=status,
                plan_id=current.plan_id,
                task_ids=current.task_ids,
                error=current.error,
                metadata=current.metadata,
                created_at=current.created_at,
            )
        )
        self._log("info", f"state.{status.value}", request_id, message)

    def _log(
        self,
        level: str,
        action: str,
        request_id: str,
        message: str,
        **metadata: Any,
    ) -> StructuredLog:
        entry = StructuredLog(
            sequence=self._next_log,
            level=level,
            action=action,
            request_id=request_id,
            message=message,
            metadata=metadata,
        )
        self._next_log += 1
        self._logs.append(entry)
        return entry

    def _logs_for(self, request_id: str) -> tuple[Mapping[str, Any], ...]:
        return tuple(log.to_dict() for log in self._logs if log.request_id == request_id)

    def _error_result(self, record: RequestRecord) -> OrchestrationResult:
        return OrchestrationResult(
            request_id=record.request_id,
            status=RequestStatus.FAILED,
            goal=None,
            plan_id=record.plan_id,
            plan_status=None,
            final_task_status=None,
            task_ids=record.task_ids,
            error=record.error,
            logs=self._logs_for(record.request_id),
        )


ProductionOrchestrator = Orchestrator
