from functools import lru_cache

from fastapi import APIRouter
from pydantic import BaseModel, Field

from rag.shared.backend_legacy.indexer import RagIndexer
from rag.shared.backend_legacy.retriever import RagRetriever


router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=6, ge=1, le=50)


@lru_cache
def get_indexer() -> RagIndexer:
    return RagIndexer()


@lru_cache
def get_retriever() -> RagRetriever:
    return RagRetriever()


def reset_route_state() -> None:
    """Clear cached route services for tests and config reloads."""
    get_indexer.cache_clear()
    get_retriever.cache_clear()


@router.post("/search")
def search(payload: SearchRequest) -> dict[str, object]:
    return {"chunks": get_retriever().search(payload.query, payload.limit)}


@router.post("/reindex")
def reindex() -> dict[str, object]:
    count = get_indexer().reindex_all()
    return {"status": "indexed", "chunks": count}
