from fastapi import APIRouter
from pydantic import BaseModel

from backend.rag.indexer import RagIndexer
from backend.rag.retriever import RagRetriever


router = APIRouter()
indexer = RagIndexer()
retriever = RagRetriever()


class SearchRequest(BaseModel):
    query: str
    limit: int = 6


@router.post("/search")
def search(payload: SearchRequest) -> dict[str, object]:
    return {"chunks": retriever.search(payload.query, payload.limit)}


@router.post("/reindex")
def reindex() -> dict[str, object]:
    count = indexer.reindex_all()
    return {"status": "indexed", "chunks": count}
