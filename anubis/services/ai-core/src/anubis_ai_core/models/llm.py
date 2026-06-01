from __future__ import annotations

from pydantic import BaseModel, Field


class LlmResponse(BaseModel):
    content: str = Field(min_length=1)
    tool_calls: list[dict] = Field(default_factory=list)
