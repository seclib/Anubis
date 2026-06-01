from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

ActionType = Literal["tool_call", "respond"]
ToolName = Literal["web_search", "memory_retrieve"]


class ToolCall(BaseModel):
    tool_name: ToolName
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentStep(BaseModel):
    observation: str = Field(min_length=1, max_length=4000)
    reasoning_summary: str = Field(min_length=1, max_length=800)
    action_type: ActionType
    tool_call: ToolCall | None = None
    final_output: str | None = Field(default=None, max_length=12000)
    confidence_score: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_payload(self) -> AgentStep:
        if self.action_type == "tool_call" and self.tool_call is None:
            raise ValueError("tool_call is required")
        if self.action_type == "respond" and not self.final_output:
            raise ValueError("final_output is required")
        return self


class MemoryDecision(BaseModel):
    should_store: bool
    reason: str


class AgentRunRequest(BaseModel):
    input: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = None
    max_steps: int = Field(default=4, ge=1, le=8)


class AgentRunResponse(BaseModel):
    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    final_output: str
    memory_decision: MemoryDecision
    steps: list[AgentStep]
    tool_results: list[dict[str, Any]]
