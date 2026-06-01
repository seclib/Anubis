"""RAG API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from rag.service import get_rag_service
from retrieval.schemas import IngestRequest, RetrievalRequest

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/query")
@router.post("/retrieve")
async def rag_query(payload: RetrievalRequest) -> dict[str, Any]:
    return get_rag_service().query(
        payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
        generate_answer=payload.generate_answer,
    )


@router.post("/ingest")
async def rag_ingest(payload: IngestRequest) -> dict[str, Any]:
    return get_rag_service().ingest(
        title=payload.title,
        content=payload.content,
        source_url=payload.source_url,
        folder=payload.folder,
        metadata=payload.metadata,
    )


@router.post("/ingest/obsidian")
async def rag_ingest_obsidian(
    limit: int | None = None,
    force: bool = False,
    index_qdrant: bool = True,
) -> dict[str, Any]:
    return get_rag_service().ingest_obsidian(
        limit=limit,
        force=force,
        index_qdrant=index_qdrant,
    )


__all__ = ["router"]
