"""Qdrant management API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from rag.service import get_rag_service

router = APIRouter(prefix="/qdrant", tags=["qdrant"])


@router.get("/health")
async def qdrant_health() -> dict[str, Any]:
    return get_rag_service().health().get("qdrant", {})


@router.post("/collections/ensure")
async def qdrant_ensure(recreate: bool = False) -> dict[str, Any]:
    return get_rag_service().ensure_qdrant(recreate=recreate)


@router.post("/index")
async def qdrant_index(limit: int | None = None) -> dict[str, Any]:
    return get_rag_service().index_qdrant(limit=limit)


__all__ = ["router"]
