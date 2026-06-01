"""FastAPI background loop orchestration."""

from __future__ import annotations

import asyncio
from typing import Any

from config import CONTINUOUS_RUN
from workers.maintenance_jobs import get_background_loop


def start_background_services(app: Any) -> dict[str, Any]:
    if not CONTINUOUS_RUN:
        app.state.background_task = None
        return {"enabled": False, "status": "disabled"}
    loop = get_background_loop()
    task = asyncio.create_task(loop.run_forever())
    app.state.background_task = task
    return {"enabled": True, "status": "started"}


async def stop_background_services(app: Any) -> dict[str, Any]:
    task = getattr(app.state, "background_task", None)
    if task is None:
        return {"enabled": False, "status": "not-running"}
    get_background_loop().stop()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    return {"enabled": True, "status": "stopped"}


__all__ = ["start_background_services", "stop_background_services"]
