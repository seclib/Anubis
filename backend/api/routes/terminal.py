from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from anubis.distributed import AgentType, ResourceLimits, TerminalService


router = APIRouter()


class CreateTerminalSessionRequest(BaseModel):
    task_id: str = Field(min_length=1)
    agent_type: AgentType = AgentType.EXECUTOR


class RunTerminalCommandRequest(BaseModel):
    command: str = Field(min_length=1)


@lru_cache
def get_terminal_service() -> TerminalService:
    return TerminalService(default_limits=ResourceLimits(cpu_seconds=2, memory_mb=8192, timeout_seconds=5.0))


def reset_route_state() -> None:
    get_terminal_service.cache_clear()


@router.post("/sessions")
def create_session(payload: CreateTerminalSessionRequest) -> dict[str, object]:
    session = get_terminal_service().create_session(payload.task_id, agent_type=payload.agent_type)
    return {"session": session.to_dict()}


@router.post("/sessions/{session_id}/commands")
def run_command(session_id: str, payload: RunTerminalCommandRequest) -> dict[str, object]:
    try:
        return get_terminal_service().run_command(session_id, payload.command).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/events")
def events(session_id: str, after_event_id: str | None = None) -> dict[str, object]:
    try:
        get_terminal_service().session_snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "events": [
            event.to_dict()
            for event in get_terminal_service().events(session_id, after_event_id=after_event_id)
        ]
    }


@router.get("/sessions/{session_id}")
def snapshot(session_id: str) -> dict[str, object]:
    try:
        return get_terminal_service().session_snapshot(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/logs")
def task_logs(task_id: str) -> dict[str, object]:
    return {"events": [event.to_dict() for event in get_terminal_service().task_logs(task_id)]}
