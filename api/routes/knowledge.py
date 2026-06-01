"""Knowledge maintenance API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from knowledge.service import get_knowledge_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/health")
async def knowledge_health() -> dict[str, Any]:
    return get_knowledge_service().vault_health()


@router.post("/maintain")
async def knowledge_maintain(apply: bool = True) -> dict[str, Any]:
    return get_knowledge_service().maintain(apply=apply)


@router.get("/gaps")
async def knowledge_gaps() -> dict[str, Any]:
    return {"gaps": get_knowledge_service().detect_gaps()}


__all__ = ["router"]
