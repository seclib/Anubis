"""Background loop for crawler, Obsidian ingestion, Qdrant indexing, and knowledge repair."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from config import OSINT_CRAWLER_ENABLED
from crawler.service import get_crawler_service
from knowledge.service import get_knowledge_service
from rag.service import get_rag_service

logger = logging.getLogger(__name__)


class BackgroundMaintenanceLoop:
    def __init__(self, *, interval_seconds: int = 3600) -> None:
        self.interval_seconds = max(60, int(interval_seconds))
        self._running = False
        self._last_result: dict[str, Any] = {}

    @property
    def last_result(self) -> dict[str, Any]:
        return self._last_result

    async def run_forever(self) -> None:
        self._running = True
        while self._running:
            self._last_result = await self.run_once()
            await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        self._running = False

    async def run_once(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        try:
            result["obsidian_ingestion"] = await asyncio.to_thread(
                get_rag_service().ingest_obsidian,
                limit=None,
                force=False,
                index_qdrant=True,
            )
        except Exception as exc:
            logger.exception("Background Obsidian ingestion failed")
            result["obsidian_ingestion"] = {"ok": False, "error": str(exc)}

        try:
            result["knowledge_maintenance"] = await asyncio.to_thread(
                get_knowledge_service().maintain,
                apply=True,
            )
        except Exception as exc:
            logger.exception("Background knowledge maintenance failed")
            result["knowledge_maintenance"] = {"ok": False, "error": str(exc)}

        if OSINT_CRAWLER_ENABLED:
            try:
                result["crawler"] = await get_crawler_service().crawl(
                    query="cybersecurity threat intelligence OSINT research",
                    seeds=[],
                    max_pages=5,
                    max_depth=1,
                    ingest=True,
                    workers=4,
                )
            except Exception as exc:
                logger.exception("Background crawler failed")
                result["crawler"] = {"ok": False, "error": str(exc)}
        else:
            result["crawler"] = {"ok": True, "status": "disabled"}

        return result


_LOOP = BackgroundMaintenanceLoop()


def get_background_loop() -> BackgroundMaintenanceLoop:
    return _LOOP


__all__ = ["BackgroundMaintenanceLoop", "get_background_loop"]

