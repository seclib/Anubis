"""Crawler request and record schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CrawlRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: str = "cybersecurity research"
    seeds: list[str] = Field(default_factory=list)
    max_pages: int = 10
    max_depth: int = 1
    workers: int = 8
    ingest: bool = True


class CrawlResult(BaseModel):
    url: str
    status_code: int | None = None
    title: str = ""
    text: str = ""
    links: list[str] = Field(default_factory=list)
    quality_score: float = 0.0
    content_hash: str = ""
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["CrawlRequest", "CrawlResult"]
