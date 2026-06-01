"""Service health aggregation."""

from __future__ import annotations

from typing import Any

from services.container import get_container


def readiness_snapshot() -> dict[str, Any]:
    return {"status": "ready", "services": get_container().health()}


__all__ = ["readiness_snapshot"]

