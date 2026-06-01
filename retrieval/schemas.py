"""Retrieval data contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: str
    top_k: int = 8
    filters: dict[str, Any] = Field(default_factory=dict)
    generate_answer: bool = False


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    content: str
    source_url: str | None = None
    folder: str = "Ingested"
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["IngestRequest", "RetrievalRequest"]

