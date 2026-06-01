"""Startup orchestration for the Anubis platform."""

from __future__ import annotations

from typing import Any

from core.logging import configure_logging
from services.container import get_container


def startup_services() -> dict[str, Any]:
    configure_logging()
    container = get_container()
    health = container.health()
    qdrant = container.rag.ensure_qdrant(recreate=False)
    obsidian = container.rag.ingest_obsidian(limit=None, force=False, index_qdrant=True)
    return {
        "health": health,
        "qdrant": qdrant,
        "obsidian_ingestion": obsidian,
    }


__all__ = ["startup_services"]

