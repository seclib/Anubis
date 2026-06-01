import asyncio
from functools import lru_cache

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.agent.async_loop import AsyncAgentLoop
from backend.rag.indexer import RagIndexer
from backend.rag.retriever import RagRetriever


router = APIRouter()


class AskRequest(BaseModel):
    task: str = Field(min_length=1)
    max_rounds: int = Field(default=2, ge=1, le=5)


class MemoryRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=6, ge=1, le=50)


@lru_cache
def get_indexer() -> RagIndexer:
    return RagIndexer()


@lru_cache
def get_retriever() -> RagRetriever:
    return RagRetriever()


def reset_route_state() -> None:
    get_indexer.cache_clear()
    get_retriever.cache_clear()


@router.post("/ask")
async def ask(payload: AskRequest) -> dict[str, object]:
    return await AsyncAgentLoop(max_rounds=payload.max_rounds).run(payload.task)


@router.post("/sync")
async def sync() -> dict[str, object]:
    chunks = await asyncio.to_thread(get_indexer().reindex_all)
    return {"status": "indexed", "chunks": chunks}


@router.post("/memory")
async def memory(payload: MemoryRequest) -> dict[str, object]:
    chunks = await asyncio.to_thread(get_retriever().search, payload.query, payload.limit)
    return {"query": payload.query, "chunks": chunks}
