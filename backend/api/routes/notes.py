from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.vault.service import VaultService


router = APIRouter()
vault = VaultService()


class NoteWrite(BaseModel):
    path: str
    content: str


@router.get("")
def list_notes() -> list[dict[str, str]]:
    return vault.list_notes()


@router.get("/{path:path}")
def read_note(path: str) -> dict[str, str]:
    try:
        return {"path": path, "content": vault.read_note(path)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Note not found") from exc


@router.put("")
def write_note(payload: NoteWrite) -> dict[str, str]:
    vault.write_note(payload.path, payload.content)
    return {"status": "written", "path": payload.path}
