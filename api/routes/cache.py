"""Cache management API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from services.container import get_container

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/health")
async def cache_health() -> dict[str, Any]:
    return get_container().cache.health()


@router.post("/invalidate")
async def cache_invalidate(query: str | None = None, include_embeddings: bool = False) -> dict[str, Any]:
    return get_container().cache.invalidate(query=query, include_embeddings=include_embeddings)


__all__ = ["router"]

