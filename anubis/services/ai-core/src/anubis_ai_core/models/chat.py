from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=20000)
    workspace_id: str | None = Field(default=None, max_length=120)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RagSource(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    score: float
    excerpt: str


class ToolExecutionLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool_name: str
    status: Literal["pending", "running", "succeeded", "failed"]
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    summary: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    sources: list[RagSource] = Field(default_factory=list)
    tool_logs: list[ToolExecutionLog] = Field(default_factory=list)
    request_id: str
