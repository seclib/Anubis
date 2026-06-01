"""Admin API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from monitoring.metrics import metrics_snapshot

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    return metrics_snapshot()


__all__ = ["router"]
