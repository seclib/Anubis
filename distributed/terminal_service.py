"""Sandbox-aware integrated terminal service for ANUBIS."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock
from typing import Any
from uuid import uuid4

from anubis.distributed.contracts import AgentType
from anubis.distributed.permission_manager import PermissionManager, ToolExecutionContext
from anubis.distributed.sandbox_runtime import IsolatedToolExecutor, ResourceLimits, SandboxContext, SandboxRuntime


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TerminalEventType(StrEnum):
    SESSION_CREATED = "session_created"
    COMMAND_STARTED = "command_started"
    OUTPUT = "output"
    COMMAND_COMPLETED = "command_completed"
    COMMAND_DENIED = "command_denied"


@dataclass(frozen=True)
class TerminalEvent:
    event_id: str
    session_id: str
    task_id: str
    event_type: TerminalEventType
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["event_type"] = self.event_type.value
        return payload


@dataclass(frozen=True)
class TerminalCommandRecord:
    command_id: str
    command: str
    success: bool
    output: str
    code: int | None = None
    started_at: str = field(default_factory=_now_iso)
    completed_at: str = field(default_factory=_now_iso)
    permission: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TerminalSession:
    session_id: str
    task_id: str
    sandbox_id: str
    workspace: str
    agent_type: AgentType = AgentType.EXECUTOR
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["agent_type"] = self.agent_type.value
        return payload


@dataclass(frozen=True)
class TerminalCommandResult:
    session: TerminalSession
    command: TerminalCommandRecord
    events: tuple[TerminalEvent, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": self.session.to_dict(),
            "command": self.command.to_dict(),
            "events": [event.to_dict() for event in self.events],
        }


class TerminalService:
    """Runs terminal commands through sandbox and permission layers only."""

    def __init__(
        self,
        *,
        runtime: SandboxRuntime | None = None,
        executor: IsolatedToolExecutor | None = None,
        permission_manager: PermissionManager | None = None,
        default_limits: ResourceLimits | None = None,
        history_limit: int = 200,
    ) -> None:
        self.runtime = runtime or SandboxRuntime()
        self.executor = executor or IsolatedToolExecutor(runtime=self.runtime, limits=default_limits)
        self.permission_manager = permission_manager or PermissionManager()
        self.history_limit = max(1, int(history_limit))
        self._sessions: dict[str, tuple[TerminalSession, SandboxContext]] = {}
        self._history: dict[str, list[TerminalCommandRecord]] = {}
        self._events: dict[str, list[TerminalEvent]] = {}
        self._lock = RLock()

    def create_session(
        self,
        task_id: str,
        *,
        agent_type: AgentType = AgentType.EXECUTOR,
        limits: ResourceLimits | None = None,
    ) -> TerminalSession:
        context = self.runtime.create(task_id, limits)
        session = TerminalSession(
            session_id=f"terminal_{uuid4().hex}",
            task_id=task_id,
            sandbox_id=context.sandbox_id,
            workspace=str(context.workspace),
            agent_type=agent_type,
        )
        with self._lock:
            self._sessions[session.session_id] = (session, context)
            self._history.setdefault(session.session_id, [])
            self._events.setdefault(session.session_id, [])
            self._append_event(
                TerminalEvent(
                    event_id=f"terminal_event_{uuid4().hex}",
                    session_id=session.session_id,
                    task_id=task_id,
                    event_type=TerminalEventType.SESSION_CREATED,
                    payload=session.to_dict(),
                )
            )
        return session

    def run_command(self, session_id: str, command: str) -> TerminalCommandResult:
        session, context = self._get_session(session_id)
        command_id = f"terminal_command_{uuid4().hex}"
        permission_context = ToolExecutionContext(
            agent_type=session.agent_type,
            task_id=session.task_id,
            sandboxed=True,
            sandbox_id=session.sandbox_id,
            workspace=session.workspace,
        )
        decision = self.permission_manager.check("run_command", permission_context)
        started = _now_iso()
        start_event = self._record_event(
            session,
            TerminalEventType.COMMAND_STARTED,
            {"command_id": command_id, "command": command, "permission": decision.to_dict()},
        )
        if not decision.approved:
            record = TerminalCommandRecord(
                command_id=command_id,
                command=command,
                success=False,
                output=decision.reason,
                code=None,
                started_at=started,
                completed_at=_now_iso(),
                permission=decision.to_dict(),
            )
            denied_event = self._record_event(
                session,
                TerminalEventType.COMMAND_DENIED,
                {"command_id": command_id, "reason": decision.reason, "permission": decision.to_dict()},
            )
            self._append_history(session.session_id, record)
            return TerminalCommandResult(session=session, command=record, events=(start_event, denied_event))

        result = self.executor.execute(
            task_id=session.task_id,
            tool="run_command",
            tool_input={"cmd": command, "task_id": session.task_id},
            context=context,
        )
        output = str(result.output or "")
        output_event = self._record_event(
            session,
            TerminalEventType.OUTPUT,
            {
                "command_id": command_id,
                "stream": "combined",
                "text": output,
                "logs": list(result.logs),
            },
        )
        record = TerminalCommandRecord(
            command_id=command_id,
            command=command,
            success=result.success,
            output=output,
            code=result.code,
            started_at=started,
            completed_at=_now_iso(),
            permission=decision.to_dict(),
        )
        completed_event = self._record_event(
            session,
            TerminalEventType.COMMAND_COMPLETED,
            {
                "command_id": command_id,
                "success": result.success,
                "code": result.code,
                "timed_out": result.timed_out,
                "error": result.error,
            },
        )
        self._append_history(session.session_id, record)
        return TerminalCommandResult(session=session, command=record, events=(start_event, output_event, completed_event))

    def history(self, session_id: str, *, limit: int | None = None) -> tuple[TerminalCommandRecord, ...]:
        with self._lock:
            rows = tuple(self._history.get(session_id, ()))
        return rows[-max(1, int(limit or self.history_limit)) :]

    def events(self, session_id: str, *, after_event_id: str | None = None) -> tuple[TerminalEvent, ...]:
        with self._lock:
            rows = tuple(self._events.get(session_id, ()))
        if after_event_id is None:
            return rows
        for index, event in enumerate(rows):
            if event.event_id == after_event_id:
                return rows[index + 1 :]
        return rows

    def task_logs(self, task_id: str) -> tuple[TerminalEvent, ...]:
        with self._lock:
            events = [event for rows in self._events.values() for event in rows if event.task_id == task_id]
        events.sort(key=lambda item: item.created_at)
        return tuple(events)

    def session_snapshot(self, session_id: str) -> dict[str, Any]:
        session, _context = self._get_session(session_id)
        return {
            "session": session.to_dict(),
            "history": [record.to_dict() for record in self.history(session_id)],
            "events": [event.to_dict() for event in self.events(session_id)],
        }

    def _get_session(self, session_id: str) -> tuple[TerminalSession, SandboxContext]:
        with self._lock:
            value = self._sessions.get(session_id)
        if value is None:
            raise KeyError(f"terminal session not found: {session_id}")
        return value

    def _append_history(self, session_id: str, record: TerminalCommandRecord) -> None:
        with self._lock:
            rows = self._history.setdefault(session_id, [])
            rows.append(record)
            if len(rows) > self.history_limit:
                del rows[: len(rows) - self.history_limit]

    def _record_event(self, session: TerminalSession, event_type: TerminalEventType, payload: dict[str, Any]) -> TerminalEvent:
        event = TerminalEvent(
            event_id=f"terminal_event_{uuid4().hex}",
            session_id=session.session_id,
            task_id=session.task_id,
            event_type=event_type,
            payload=payload,
        )
        with self._lock:
            self._append_event(event)
        return event

    def _append_event(self, event: TerminalEvent) -> None:
        rows = self._events.setdefault(event.session_id, [])
        rows.append(event)
        if len(rows) > self.history_limit * 4:
            del rows[: len(rows) - self.history_limit * 4]


__all__ = [
    "TerminalCommandRecord",
    "TerminalCommandResult",
    "TerminalEvent",
    "TerminalEventType",
    "TerminalService",
    "TerminalSession",
]
