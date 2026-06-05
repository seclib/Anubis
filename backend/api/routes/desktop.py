from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.agent.loop import AgentLoop
from rag.shared.backend_legacy.indexer import RagIndexer
from rag.shared.backend_legacy.retriever import RagRetriever
from backend.vault.service import VaultService


router = APIRouter()


class NoteWrite(BaseModel):
    path: str = Field(min_length=1)
    content: str


class DocumentIngest(BaseModel):
    name: str = Field(min_length=1)
    content: str = Field(min_length=1)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=8, ge=1, le=30)


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1)


@lru_cache
def get_vault() -> VaultService:
    return VaultService()


@lru_cache
def get_indexer() -> RagIndexer:
    return RagIndexer()


@lru_cache
def get_retriever() -> RagRetriever:
    return RagRetriever()


@lru_cache
def get_agent() -> AgentLoop:
    return AgentLoop()


def reset_route_state() -> None:
    get_vault.cache_clear()
    get_indexer.cache_clear()
    get_retriever.cache_clear()
    get_agent.cache_clear()


def _safe_markdown_name(name: str) -> str:
    stem = Path(name).stem.strip().replace("/", "-").replace("\\", "-")
    if not stem:
        stem = "Untitled"
    return f"library/{stem}.md"


def _index_all() -> None:
    get_indexer().reindex_all()


@router.get("/library")
def library() -> dict[str, object]:
    return {"items": get_vault().list_notes()}


@router.post("/library/ingest")
def ingest_document(payload: DocumentIngest, background_tasks: BackgroundTasks) -> dict[str, object]:
    path = _safe_markdown_name(payload.name)
    content = payload.content.strip()
    if not content.startswith("#"):
        content = f"# {Path(payload.name).stem or 'Imported document'}\n\n{content}"
    try:
        get_vault().write_note(path, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(_index_all)
    return {"status": "saved", "path": path}


@router.get("/notes")
def list_notes() -> list[dict[str, str]]:
    return get_vault().list_notes()


@router.get("/notes/{path:path}")
def read_note(path: str) -> dict[str, str]:
    try:
        return {"path": path, "content": get_vault().read_note(path)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Note not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/notes")
def write_note(payload: NoteWrite, background_tasks: BackgroundTasks) -> dict[str, str]:
    try:
        get_vault().write_note(payload.path, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(_index_all)
    return {"status": "saved", "path": payload.path}


@router.post("/notes")
def create_note(background_tasks: BackgroundTasks) -> dict[str, str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = f"notes/Untitled-{stamp}.md"
    get_vault().write_note(path, "# Untitled\n\n")
    background_tasks.add_task(_index_all)
    return {"status": "created", "path": path, "content": "# Untitled\n\n"}


@router.post("/search")
def search(payload: SearchRequest) -> dict[str, object]:
    chunks = get_retriever().search(payload.query, payload.limit)
    results = [
        {
            "path": chunk.get("path", ""),
            "title": chunk.get("heading") or Path(str(chunk.get("path", ""))).stem,
            "excerpt": chunk.get("text", ""),
            "score": chunk.get("score", 0),
        }
        for chunk in chunks
    ]
    return {"query": payload.query, "results": results}


@router.post("/assistant/chat")
def assistant_chat(payload: AssistantRequest) -> dict[str, object]:
    result = get_agent().chat(payload.message)
    return {
        "answer": result.get("answer", ""),
        "sources": [
            {
                "path": chunk.get("path", ""),
                "title": chunk.get("heading") or Path(str(chunk.get("path", ""))).stem,
                "excerpt": chunk.get("text", ""),
            }
            for chunk in result.get("chunks_used", [])
        ],
    }
