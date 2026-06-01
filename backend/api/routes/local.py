import logging
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent.loop import AgentLoop
from backend.rag.embedder import LocalEmbedder
from backend.rag.indexer import RagIndexer
from backend.rag.retriever import RagRetriever
from backend.vault.service import VaultService


router = APIRouter(tags=["local-api"])
logger = logging.getLogger("anubis.api")


class FilePathRequest(BaseModel):
    file: str = Field(min_length=1)


class WriteRequest(FilePathRequest):
    content: str
    index: bool = True


class UpdateRequest(FilePathRequest):
    patch: str = Field(min_length=1)
    index: bool = True


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = 6


class EmbedRequest(BaseModel):
    text: str = Field(min_length=1)


class AgentQueryRequest(BaseModel):
    query: str = Field(min_length=1)


@lru_cache
def get_vault() -> VaultService:
    return VaultService()


@lru_cache
def get_retriever() -> RagRetriever:
    return RagRetriever()


@lru_cache
def get_embedder() -> LocalEmbedder:
    return LocalEmbedder()


@lru_cache
def get_indexer() -> RagIndexer:
    return RagIndexer()


@lru_cache
def get_agent() -> AgentLoop:
    return AgentLoop()


def reset_route_state() -> None:
    """Clear cached route services for tests and config reloads."""
    get_vault.cache_clear()
    get_retriever.cache_clear()
    get_embedder.cache_clear()
    get_indexer.cache_clear()
    get_agent.cache_clear()


@router.get("/files")
def files() -> dict[str, object]:
    notes = get_vault().list_notes()
    logger.info("files count=%s", len(notes))
    return {"files": notes}


@router.post("/read")
def read(payload: FilePathRequest) -> dict[str, str]:
    try:
        content = get_vault().read_note(payload.file)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Markdown file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("read file=%s bytes=%s", payload.file, len(content.encode("utf-8")))
    return {"file": payload.file, "content": content}


@router.post("/write")
def write(payload: WriteRequest) -> dict[str, object]:
    try:
        get_vault().write_note(payload.file, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    indexed_chunks = get_indexer().reindex_all() if payload.index else None
    logger.info("write file=%s indexed_chunks=%s", payload.file, indexed_chunks)
    return {"status": "written", "file": payload.file, "indexed_chunks": indexed_chunks}


@router.post("/update")
def update(payload: UpdateRequest) -> dict[str, object]:
    try:
        current = get_vault().read_note(payload.file)
        get_vault().write_note(payload.file, f"{current.rstrip()}\n\n{payload.patch.strip()}\n")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Markdown file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    indexed_chunks = get_indexer().reindex_all() if payload.index else None
    logger.info("update file=%s indexed_chunks=%s", payload.file, indexed_chunks)
    return {"status": "updated", "file": payload.file, "indexed_chunks": indexed_chunks}


@router.post("/search_rag")
def search_rag(payload: SearchRequest) -> dict[str, object]:
    chunks = get_retriever().search(payload.query, payload.limit)
    logger.info("search_rag query=%r chunks=%s", payload.query, len(chunks))
    return {"query": payload.query, "chunks": chunks}


@router.post("/embed")
def embed(payload: EmbedRequest) -> dict[str, object]:
    vector = get_embedder().embed(payload.text)
    logger.info("embed chars=%s dims=%s", len(payload.text), len(vector))
    return {"embedding": vector, "dimensions": len(vector)}


@router.post("/agent_query")
def agent_query(payload: AgentQueryRequest) -> dict[str, object]:
    result = get_agent().chat(payload.query)
    logger.info("agent_query query=%r chunks=%s", payload.query, len(result.get("chunks_used", [])))
    return result
