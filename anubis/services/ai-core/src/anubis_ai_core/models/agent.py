from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

AgentActionType = Literal["tool_call", "retrieve_memory", "respond", "store_memory"]
AllowedToolName = Literal["web_search", "rag_query", "file_read", "file_write", "memory_store", "memory_retrieve"]


class AgentMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1, max_length=50000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryContextItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    content: str = Field(max_length=12000)
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentToolResult(BaseModel):
    tool_name: AllowedToolName
    status: Literal["succeeded", "failed"]
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolCall(BaseModel):
    tool_name: AllowedToolName
    input_schema: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    async_flag: bool = False


class AgentStep(BaseModel):
    observation: str = Field(min_length=1, max_length=8000)
    reasoning_summary: str = Field(min_length=1, max_length=1200)
    action_type: AgentActionType
    tool_call: ToolCall | None = None
    final_output: str | None = Field(default=None, max_length=50000)
    confidence_score: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_action_payload(self) -> AgentStep:
        if self.action_type in {"tool_call", "store_memory"} and self.tool_call is None:
            raise ValueError("tool_call is required for tool_call and store_memory actions")
        if self.action_type == "respond" and not self.final_output:
            raise ValueError("final_output is required for respond actions")
        return self


class AgentState(BaseModel):
    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    messages: list[AgentMessage] = Field(default_factory=list)
    memory_context: list[MemoryContextItem] = Field(default_factory=list)
    tool_results: list[AgentToolResult] = Field(default_factory=list)
    step_counter: int = 0
    termination_flag: bool = False


class AgentTraceEvent(BaseModel):
    step_id: str
    conversation_id: str
    step_number: int
    input_state: dict[str, Any]
    decision_json: dict[str, Any] | None = None
    tool_outputs: list[dict[str, Any]] = Field(default_factory=list)
    timing_ms: float
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentRunRequest(BaseModel):
    conversation_id: str | None = None
    input: str = Field(min_length=1, max_length=20000)
    max_steps: int = Field(default=12, ge=1, le=12)
    retrieve_initial_memory: bool = True


class AgentRunResponse(BaseModel):
    conversation_id: str
    final_output: str
    state: AgentState
    steps: list[AgentStep]
    trace: list[AgentTraceEvent]
    request_id: str
