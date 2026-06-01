from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.vault.service import VaultService


router = APIRouter()


class NoteWrite(BaseModel):
    path: str = Field(min_length=1)
    content: str


@lru_cache
def get_vault() -> VaultService:
    return VaultService()


def reset_route_state() -> None:
    """Clear cached route services for tests and config reloads."""
    get_vault.cache_clear()


@router.get("")
def list_notes() -> list[dict[str, str]]:
    return get_vault().list_notes()


@router.get("/{path:path}")
def read_note(path: str) -> dict[str, str]:
    try:
        return {"path": path, "content": get_vault().read_note(path)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Note not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("")
def write_note(payload: NoteWrite) -> dict[str, str]:
    try:
        get_vault().write_note(payload.path, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "written", "path": payload.path}
