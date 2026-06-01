from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

OrchestrationToolName = Literal["web_search", "rag_query", "file_read", "file_write", "memory_retrieve"]
ExecutionStatus = Literal["success", "failed"]
IssueType = Literal["missing_info", "error", "hallucination", "weak_reasoning"]
Severity = Literal["low", "medium", "high"]


class OrchestrationSession(BaseModel):
    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    user_input: str = Field(min_length=1, max_length=20000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlannerSubtask(BaseModel):
    id: int = Field(ge=1)
    task: str = Field(min_length=1, max_length=2000)
    tool_needed: bool
    tool_name: OrchestrationToolName | None = None
    dependencies: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tool_contract(self) -> PlannerSubtask:
        if self.tool_needed and self.tool_name is None:
            raise ValueError("tool_name is required when tool_needed is true")
        if not self.tool_needed and self.tool_name is not None:
            raise ValueError("tool_name must be null when tool_needed is false")
        return self


class PlannerOutput(BaseModel):
    goal: str = Field(min_length=1, max_length=3000)
    subtasks: list[PlannerSubtask] = Field(min_length=1, max_length=12)
    execution_order: list[int] = Field(min_length=1, max_length=12)
    risk_notes: str = Field(default="", max_length=3000)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_execution_order(self) -> PlannerOutput:
        subtask_ids = {subtask.id for subtask in self.subtasks}
        if set(self.execution_order) != subtask_ids:
            raise ValueError("execution_order must include each subtask id exactly once")
        for subtask in self.subtasks:
            missing = set(subtask.dependencies) - subtask_ids
            if missing:
                raise ValueError(f"Subtask {subtask.id} has unknown dependencies: {sorted(missing)}")
        return self


class ExecutorStepTrace(BaseModel):
    step_id: int
    tool_used: OrchestrationToolName | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    status: ExecutionStatus


class ExecutorOutput(BaseModel):
    executed_steps: list[ExecutorStepTrace] = Field(default_factory=list, max_length=12)
    draft_response: str = Field(default="", max_length=50000)
    missing_info: list[str] = Field(default_factory=list, max_length=20)
    execution_errors: list[str] = Field(default_factory=list, max_length=20)


class CriticIssue(BaseModel):
    type: IssueType
    description: str = Field(min_length=1, max_length=2000)
    severity: Severity


class CriticOutput(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    approved: bool
    issues: list[CriticIssue] = Field(default_factory=list, max_length=20)
    fix_instructions: list[str] = Field(default_factory=list, max_length=20)
    final_response: str | None = Field(default=None, max_length=50000)

    @model_validator(mode="after")
    def validate_approval(self) -> CriticOutput:
        if self.approved and not self.final_response:
            raise ValueError("final_response is required when approved is true")
        if self.approved and self.issues:
            raise ValueError("approved critic output cannot include issues")
        if not self.approved and not self.fix_instructions:
            raise ValueError("fix_instructions are required when approved is false")
        return self


class OrchestrationTraceEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    loop_iteration: int
    stage: Literal["session_manager", "planner", "executor", "critic", "final_response", "memory_write_decision"]
    payload: dict[str, Any]
    latency_ms: float
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrchestratorRunRequest(BaseModel):
    conversation_id: str | None = None
    input: str = Field(min_length=1, max_length=20000)
    max_iterations: int = Field(default=3, ge=1, le=3)
    replay_trace: list[OrchestrationTraceEvent] | None = None


class MemoryWriteDecision(BaseModel):
    should_store: bool
    reason: str = Field(min_length=1, max_length=2000)
    candidate: str | None = Field(default=None, max_length=12000)
    namespace: str = Field(default="orchestrator", max_length=120)
    requires_user_confirmation: bool = True

    @model_validator(mode="after")
    def validate_candidate(self) -> MemoryWriteDecision:
        if self.should_store and not self.candidate:
            raise ValueError("candidate is required when should_store is true")
        return self


class OrchestratorRunResponse(BaseModel):
    conversation_id: str
    final_response: str
    approved: bool
    iterations: int
    session: OrchestrationSession
    plan: PlannerOutput
    executor_output: ExecutorOutput
    critic_output: CriticOutput
    memory_write_decision: MemoryWriteDecision
    trace: list[OrchestrationTraceEvent]
    request_id: str
