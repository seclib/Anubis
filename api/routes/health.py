"""Health API router."""

from __future__ import annotations

from fastapi import APIRouter

from services.health import readiness_snapshot

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready() -> dict[str, object]:
    return readiness_snapshot()


__all__ = ["router"]
