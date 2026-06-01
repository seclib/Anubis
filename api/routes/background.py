"""Background loop API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from workers.maintenance_jobs import get_background_loop

router = APIRouter(prefix="/background", tags=["background"])


@router.post("/run-once")
async def run_once() -> dict[str, Any]:
    return await get_background_loop().run_once()


@router.get("/status")
async def status() -> dict[str, Any]:
    return {"last_result": get_background_loop().last_result}


__all__ = ["router"]

