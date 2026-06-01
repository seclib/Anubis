"""FastAPI lifespan startup helpers."""

from __future__ import annotations

import logging
from typing import Any

from services.container import get_container
from services.background import start_background_services, stop_background_services
from services.startup import startup_services

logger = logging.getLogger(__name__)


def initialize_app_state(app: Any) -> dict[str, Any]:
    app.state.services = get_container()
    app.state.retrieval = app.state.services.rag.retrieval
    app.state.crawler = app.state.services.crawler
    app.state.knowledge = app.state.services.knowledge
    app.state.redis = app.state.services.redis
    try:
        app.state.startup_health = startup_services()
        app.state.background_health = start_background_services(app)
    except Exception as exc:
        logger.warning("Startup orchestration degraded: %s", exc)
        app.state.startup_health = {
            "degraded": True,
            "error": str(exc),
            "services": app.state.services.health(),
        }
        app.state.background_health = {"enabled": False, "error": str(exc)}
    return app.state.startup_health


async def shutdown_app_state(app: Any) -> dict[str, Any]:
    return await stop_background_services(app)


__all__ = ["initialize_app_state", "shutdown_app_state"]
