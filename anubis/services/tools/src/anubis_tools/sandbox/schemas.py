from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class SecureToolExecutionRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=120)


class SecureToolError(BaseModel):
    error: Literal[True] = True
    code: str
    message: str
    request_id: str


class SecureToolExecutionResult(BaseModel):
    tool_name: str
    request_id: str
    status: Literal["succeeded", "failed"]
    output: dict[str, Any] = Field(default_factory=dict)
    error: SecureToolError | None = None


class ToolPermission(BaseModel):
    network: bool = False
    filesystem: Literal[False, "read_only", "read_write"] = False
    shell: bool = False
    allowed_paths: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    max_output_bytes: int = Field(default=64000, ge=1024, le=1000000)


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str
    tool_name: str
    parameters: dict[str, Any]
    status: Literal["succeeded", "failed", "denied"]
    duration_ms: float
    output_hash: str
    error_code: str | None = None
    previous_hash: str
    event_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
