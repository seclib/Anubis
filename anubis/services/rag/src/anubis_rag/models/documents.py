from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class DocumentInput(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=500000)
    source_type: Literal["markdown", "note", "text"] = "text"
    metadata: dict[str, str] = Field(default_factory=dict)


class Chunk(BaseModel):
    id: str
    document_id: str
    title: str
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=50)


class IngestRequest(BaseModel):
    documents: list[DocumentInput] = Field(min_length=1, max_length=100)


class RagSource(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    score: float
    excerpt: str


class RetrievedChunk(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    text: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    results: list[RagSource]


class IngestResponse(BaseModel):
    documents: int
    chunks: int
