from __future__ import annotations

from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field


ToolFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ToolDefinition(BaseModel):
    name: str
    parameters_schema: dict[str, Any]
    timeout_seconds: float = Field(default=5.0, gt=0, le=20)


class RegisteredTool(BaseModel):
    definition: ToolDefinition
    executor: ToolFn

    model_config = {"arbitrary_types_allowed": True}
