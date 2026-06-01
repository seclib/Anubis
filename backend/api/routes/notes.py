from functools import lru_cache

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.vault.service import VaultService
from backend.rag.indexer import RagIndexer


router = APIRouter()


class NoteWrite(BaseModel):
    path: str = Field(min_length=1)
    content: str


@lru_cache
def get_vault() -> VaultService:
    return VaultService()


@lru_cache
def get_indexer() -> RagIndexer:
    return RagIndexer()


def reset_route_state() -> None:
    """Clear cached route services for tests and config reloads."""
    get_vault.cache_clear()
    get_indexer.cache_clear()


def _index_all() -> None:
    get_indexer().reindex_all()


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
def write_note(payload: NoteWrite, background_tasks: BackgroundTasks) -> dict[str, str]:
    try:
        get_vault().write_note(payload.path, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(_index_all)
    return {"status": "saved", "path": payload.path}
