"""Crawler API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from crawler.schemas import CrawlRequest
from crawler.service import get_crawler_service

router = APIRouter(prefix="/crawl", tags=["crawler"])


@router.post("/jobs")
async def crawl_job(payload: CrawlRequest) -> dict[str, Any]:
    return await get_crawler_service().crawl(
        query=payload.query,
        seeds=payload.seeds,
        max_pages=payload.max_pages,
        max_depth=payload.max_depth,
        ingest=payload.ingest,
        workers=payload.workers,
    )


__all__ = ["router"]
