"""Global kill switch and recovery controls for ANUBIS execution."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any, Protocol

from anubis.distributed.contracts import EventType, OrchestrationEvent
from anubis.distributed.event_bus import EventBus


class KillSwitchActiveError(RuntimeError):
    """Raised when execution is attempted while ANUBIS is frozen."""


class KillSwitchState(StrEnum):
    ARMED = "armed"
    TRIGGERED = "triggered"
    RECOVERY = "recovery"


class KillTrigger(StrEnum):
    MANUAL = "manual"
    REPEATED_FAILURES = "repeated_failures"
    UNSAFE_FILE_ACCESS = "unsafe_file_access"
    SYSTEM_INSTABILITY = "system_instability"


class RecoveryMode(StrEnum):
    INACTIVE = "inactive"
    INSPECTION_ONLY = "inspection_only"


class ProcessHandle(Protocol):
    def terminate(self) -> None: ...

    def kill(self) -> None: ...


@dataclass(frozen=True)
class KillSwitchRecord:
    trigger: KillTrigger
    reason: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger.value,
            "reason": self.reason,
            "source": self.source,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class KillSwitchStatus:
    state: KillSwitchState
    recovery_mode: RecoveryMode
    execution_allowed: bool
    queue_processing_allowed: bool
    triggered_by: KillTrigger | None = None
    reason: str | None = None
    source: str = ""
    active_processes: tuple[str, ...] = ()
    cancelled_processes: tuple[str, ...] = ()
    frozen_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "recovery_mode": self.recovery_mode.value,
            "execution_allowed": self.execution_allowed,
            "queue_processing_allowed": self.queue_processing_allowed,
            "triggered_by": self.triggered_by.value if self.triggered_by else None,
            "reason": self.reason,
            "source": self.source,
            "active_processes": list(self.active_processes),
            "cancelled_processes": list(self.cancelled_processes),
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
        }


@dataclass(frozen=True)
class RecoverySnapshot:
    record: KillSwitchRecord
    status: KillSwitchStatus
    frozen_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record": self.record.to_dict(),
            "status": self.status.to_dict(),
            "frozen_state": dict(self.frozen_state),
        }


class ProcessRegistry:
    """Tracks killable sandbox/process handles for emergency cancellation."""

    def __init__(self) -> None:
        self._processes: dict[str, ProcessHandle] = {}
        self._lock = RLock()

    def register(self, execution_id: str, process: ProcessHandle) -> None:
        if not execution_id.strip():
            raise ValueError("execution_id is required")
        with self._lock:
            self._processes[execution_id] = process

    def unregister(self, execution_id: str) -> None:
        with self._lock:
            self._processes.pop(execution_id, None)

    def active_ids(self) -> tuple[str, ...]:
        with self._lock:
            active = [execution_id for execution_id, process in self._processes.items() if _is_running(process)]
            return tuple(sorted(active))

    def cancel_all(self, *, timeout_seconds: float = 1.0) -> tuple[str, ...]:
        with self._lock:
            processes = dict(self._processes)

        cancelled: list[str] = []
        for execution_id, process in processes.items():
            if not _is_running(process):
                self.unregister(execution_id)
                continue
            _terminate_process(process, timeout_seconds)
            cancelled.append(execution_id)
            self.unregister(execution_id)
        return tuple(sorted(cancelled))


class FailureMonitor:
    """Counts repeated failures and signals when the safety threshold is crossed."""

    def __init__(self, *, threshold: int = 3) -> None:
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        self.threshold = threshold
        self._failures: list[dict[str, Any]] = []
        self._lock = RLock()

    def record_failure(self, *, source: str, reason: str, metadata: dict[str, Any] | None = None) -> bool:
        with self._lock:
            self._failures.append(
                {
                    "source": source,
                    "reason": reason,
                    "metadata": dict(metadata or {}),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            return len(self._failures) >= self.threshold

    def failures(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(dict(item) for item in self._failures)


class RecoveryStateManager:
    """Freezes system state and exposes inspection-only recovery mode."""

    def __init__(self) -> None:
        self.mode = RecoveryMode.INACTIVE
        self._snapshot: RecoverySnapshot | None = None
        self._lock = RLock()

    def enter_recovery(
        self,
        *,
        record: KillSwitchRecord,
        status: KillSwitchStatus,
        frozen_state: dict[str, Any] | None = None,
    ) -> RecoverySnapshot:
        with self._lock:
            self.mode = RecoveryMode.INSPECTION_ONLY
            self._snapshot = RecoverySnapshot(record=record, status=status, frozen_state=dict(frozen_state or {}))
            return self._snapshot

    def snapshot(self) -> RecoverySnapshot | None:
        with self._lock:
            return self._snapshot

    def assert_execution_allowed(self) -> None:
        if self.mode == RecoveryMode.INSPECTION_ONLY:
            raise KillSwitchActiveError("ANUBIS is in recovery inspection mode; execution is disabled")


class KillSwitchController:
    """Emergency shutdown controller for queues, executors, and sandboxes."""

    def __init__(
        self,
        *,
        event_bus: EventBus | None = None,
        process_registry: ProcessRegistry | None = None,
        failure_monitor: FailureMonitor | None = None,
        recovery_manager: RecoveryStateManager | None = None,
        process_cancel_timeout_seconds: float = 1.0,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.process_registry = process_registry or ProcessRegistry()
        self.failure_monitor = failure_monitor or FailureMonitor()
        self.recovery_manager = recovery_manager or RecoveryStateManager()
        self.process_cancel_timeout_seconds = process_cancel_timeout_seconds
        self._state = KillSwitchState.ARMED
        self._record: KillSwitchRecord | None = None
        self._cancelled_processes: tuple[str, ...] = ()
        self._lock = RLock()

    @property
    def state(self) -> KillSwitchState:
        with self._lock:
            return self._state

    def trigger(
        self,
        trigger: KillTrigger | str,
        reason: str,
        *,
        source: str = "",
        metadata: dict[str, Any] | None = None,
        frozen_state: dict[str, Any] | None = None,
    ) -> KillSwitchStatus:
        normalized_trigger = trigger if isinstance(trigger, KillTrigger) else KillTrigger(trigger)
        with self._lock:
            if self._state != KillSwitchState.ARMED:
                return self.status()
            self._state = KillSwitchState.TRIGGERED
            self._record = KillSwitchRecord(
                trigger=normalized_trigger,
                reason=reason,
                source=source,
                metadata=dict(metadata or {}),
            )

        cancelled = self.process_registry.cancel_all(timeout_seconds=self.process_cancel_timeout_seconds)
        with self._lock:
            self._cancelled_processes = cancelled
            self._state = KillSwitchState.RECOVERY
            status = self._status_with_recovery_mode(RecoveryMode.INSPECTION_ONLY)

        snapshot_state = {
            "active_processes_after_cancel": list(status.active_processes),
            "cancelled_processes": list(cancelled),
            **dict(frozen_state or {}),
        }
        self.recovery_manager.enter_recovery(record=self._record, status=status, frozen_state=snapshot_state)
        self._publish_trigger_event(status)
        return status

    def manual_trigger(self, reason: str, *, source: str = "operator", metadata: dict[str, Any] | None = None) -> KillSwitchStatus:
        return self.trigger(KillTrigger.MANUAL, reason, source=source, metadata=metadata)

    def record_failure(self, *, source: str, reason: str, metadata: dict[str, Any] | None = None) -> KillSwitchStatus | None:
        should_trigger = self.failure_monitor.record_failure(source=source, reason=reason, metadata=metadata)
        if not should_trigger:
            return None
        return self.trigger(
            KillTrigger.REPEATED_FAILURES,
            f"failure threshold reached: {reason}",
            source=source,
            metadata={"failures": list(self.failure_monitor.failures()), **dict(metadata or {})},
        )

    def record_unsafe_file_access(
        self,
        *,
        path: str,
        source: str,
        reason: str = "unsafe file access attempt",
        metadata: dict[str, Any] | None = None,
    ) -> KillSwitchStatus:
        return self.trigger(
            KillTrigger.UNSAFE_FILE_ACCESS,
            reason,
            source=source,
            metadata={"path": path, **dict(metadata or {})},
        )

    def record_instability(self, *, source: str, reason: str, metadata: dict[str, Any] | None = None) -> KillSwitchStatus:
        return self.trigger(KillTrigger.SYSTEM_INSTABILITY, reason, source=source, metadata=metadata)

    def assert_execution_allowed(self) -> None:
        status = self.status()
        if not status.execution_allowed:
            raise KillSwitchActiveError(f"ANUBIS execution disabled by kill switch: {status.reason}")
        self.recovery_manager.assert_execution_allowed()

    def assert_queue_processing_allowed(self) -> None:
        if not self.status().queue_processing_allowed:
            raise KillSwitchActiveError("ANUBIS task queue processing is frozen by kill switch")

    def status(self) -> KillSwitchStatus:
        with self._lock:
            return self._status_with_recovery_mode(self.recovery_manager.mode)

    def _status_with_recovery_mode(self, recovery_mode: RecoveryMode) -> KillSwitchStatus:
        record = self._record
        active_processes = self.process_registry.active_ids()
        execution_allowed = self._state == KillSwitchState.ARMED and recovery_mode == RecoveryMode.INACTIVE
        return KillSwitchStatus(
            state=self._state,
            recovery_mode=recovery_mode,
            execution_allowed=execution_allowed,
            queue_processing_allowed=execution_allowed,
            triggered_by=record.trigger if record else None,
            reason=record.reason if record else None,
            source=record.source if record else "",
            active_processes=active_processes,
            cancelled_processes=self._cancelled_processes,
            frozen_at=record.created_at if record else None,
        )

    def _publish_trigger_event(self, status: KillSwitchStatus) -> None:
        self.event_bus.publish(
            OrchestrationEvent(
                event_type=EventType.TASK_FAILED,
                task_id="global-kill-switch",
                message="ANUBIS kill switch activated",
                payload=status.to_dict(),
            )
        )


class KillSwitchGuardedExecutor:
    """Execution gate that denies delegate calls after emergency shutdown."""

    def __init__(
        self,
        controller: KillSwitchController,
        delegate: Any,
        *,
        execute_method: str = "execute",
        denial_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.controller = controller
        self.delegate = delegate
        self.execute_method = execute_method
        self.denial_factory = denial_factory or _default_denial

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        try:
            self.controller.assert_execution_allowed()
        except KillSwitchActiveError as exc:
            return self.denial_factory(str(exc))
        return getattr(self.delegate, self.execute_method)(*args, **kwargs)


def _default_denial(error: str) -> dict[str, Any]:
    return {"success": False, "output": "", "logs": ["kill switch active"], "error": error}


def _is_running(process: ProcessHandle) -> bool:
    if hasattr(process, "is_alive"):
        return bool(process.is_alive())  # type: ignore[attr-defined]
    if hasattr(process, "poll"):
        return process.poll() is None  # type: ignore[attr-defined]
    return True


def _terminate_process(process: ProcessHandle, timeout_seconds: float) -> None:
    if not _is_running(process):
        return
    process.terminate()
    if _wait(process, timeout_seconds):
        return
    if hasattr(process, "kill"):
        process.kill()
    _wait(process, timeout_seconds)


def _wait(process: ProcessHandle, timeout_seconds: float) -> bool:
    try:
        if hasattr(process, "join"):
            process.join(timeout_seconds)  # type: ignore[attr-defined]
        elif hasattr(process, "wait"):
            process.wait(timeout=timeout_seconds)  # type: ignore[attr-defined]
    except subprocess.TimeoutExpired:
        return False
    return not _is_running(process)


__all__ = [
    "FailureMonitor",
    "KillSwitchActiveError",
    "KillSwitchController",
    "KillSwitchGuardedExecutor",
    "KillSwitchRecord",
    "KillSwitchState",
    "KillSwitchStatus",
    "KillTrigger",
    "ProcessRegistry",
    "RecoveryMode",
    "RecoverySnapshot",
    "RecoveryStateManager",
]
