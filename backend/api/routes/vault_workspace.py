from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from anubis.workspace import VaultWorkspace, VaultWorkspaceError
from backend.core.config import settings


router = APIRouter()


class WriteNoteRequest(BaseModel):
    path: str = Field(min_length=1)
    content: str
    index: bool = True


@lru_cache
def get_vault_workspace() -> VaultWorkspace:
    return VaultWorkspace(settings.vault_path)


def reset_route_state() -> None:
    get_vault_workspace.cache_clear()


def vault() -> VaultWorkspace:
    return get_vault_workspace()


@router.get("/navigation")
def navigation() -> dict[str, object]:
    return {"notes": [note.to_dict() for note in vault().list_notes()]}


@router.get("/snapshot")
def snapshot() -> dict[str, object]:
    return vault().snapshot().to_dict()


@router.get("/graph")
def graph() -> dict[str, object]:
    return vault().graph().to_dict()


@router.get("/backlinks")
def backlinks(path: str = Query(min_length=1)) -> dict[str, object]:
    try:
        return {"backlinks": [backlink.to_dict() for backlink in vault().backlinks(path)]}
    except VaultWorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/search")
def search(query: str = Query(min_length=1), limit: int = Query(default=8, ge=1, le=25)) -> dict[str, object]:
    return {"results": [result.to_dict() for result in vault().search(query, limit=limit)]}


@router.get("/notes/{note_path:path}")
def read_note(note_path: str) -> dict[str, object]:
    try:
        return {"path": note_path, "content": vault().read_note(note_path)}
    except VaultWorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/notes")
def write_note(payload: WriteNoteRequest) -> dict[str, object]:
    try:
        return vault().write_note(payload.path, payload.content, index=payload.index).to_dict()
    except VaultWorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
