import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent.loop import AgentLoop
from backend.rag.embedder import LocalEmbedder
from backend.rag.indexer import RagIndexer
from backend.rag.retriever import RagRetriever
from backend.vault.service import VaultService


router = APIRouter(tags=["local-api"])
logger = logging.getLogger("anubis.api")

vault = VaultService()
retriever = RagRetriever()
embedder = LocalEmbedder()
indexer = RagIndexer()
agent = AgentLoop()


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


@router.get("/files")
def files() -> dict[str, object]:
    notes = vault.list_notes()
    logger.info("files count=%s", len(notes))
    return {"files": notes}


@router.post("/read")
def read(payload: FilePathRequest) -> dict[str, str]:
    try:
        content = vault.read_note(payload.file)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Markdown file not found") from exc
    logger.info("read file=%s bytes=%s", payload.file, len(content.encode("utf-8")))
    return {"file": payload.file, "content": content}


@router.post("/write")
def write(payload: WriteRequest) -> dict[str, object]:
    try:
        vault.write_note(payload.file, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    indexed_chunks = indexer.reindex_all() if payload.index else None
    logger.info("write file=%s indexed_chunks=%s", payload.file, indexed_chunks)
    return {"status": "written", "file": payload.file, "indexed_chunks": indexed_chunks}


@router.post("/update")
def update(payload: UpdateRequest) -> dict[str, object]:
    try:
        current = vault.read_note(payload.file)
        vault.write_note(payload.file, f"{current.rstrip()}\n\n{payload.patch.strip()}\n")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Markdown file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    indexed_chunks = indexer.reindex_all() if payload.index else None
    logger.info("update file=%s indexed_chunks=%s", payload.file, indexed_chunks)
    return {"status": "updated", "file": payload.file, "indexed_chunks": indexed_chunks}


@router.post("/search_rag")
def search_rag(payload: SearchRequest) -> dict[str, object]:
    chunks = retriever.search(payload.query, payload.limit)
    logger.info("search_rag query=%r chunks=%s", payload.query, len(chunks))
    return {"query": payload.query, "chunks": chunks}


@router.post("/embed")
def embed(payload: EmbedRequest) -> dict[str, object]:
    vector = embedder.embed(payload.text)
    logger.info("embed chars=%s dims=%s", len(payload.text), len(vector))
    return {"embedding": vector, "dimensions": len(vector)}


@router.post("/agent_query")
def agent_query(payload: AgentQueryRequest) -> dict[str, object]:
    result = agent.chat(payload.query)
    logger.info("agent_query query=%r chunks=%s", payload.query, len(result.get("chunks_used", [])))
    return result
