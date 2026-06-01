from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from anubis_rag.models.documents import RetrievedChunk

RiskType = Literal["prompt_injection", "data_poisoning", "tool_manipulation", "system_override", "benign"]
TrustLevel = Literal["high", "medium", "low"]


class SecurityFilterResult(BaseModel):
    safe: bool
    reason: str
    risk_type: RiskType
    detected_patterns: list[str] = Field(default_factory=list)


class ChunkScore(BaseModel):
    relevance_score: float = Field(ge=0.0, le=1.0)
    trust_score: float = Field(ge=0.0, le=1.0)
    injection_risk_score: float = Field(ge=0.0, le=1.0)
    freshness_score: float | None = Field(default=None, ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    trust_level: TrustLevel


class TransformedContext(BaseModel):
    facts: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removed_instructions: list[str] = Field(default_factory=list)
    trust_level: TrustLevel


class SecuredChunk(BaseModel):
    chunk: RetrievedChunk
    security: SecurityFilterResult
    score: ChunkScore
    transformed: TransformedContext
    allowed_for_prompt: bool


class SafeContextSource(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    final_score: float
    trust_level: TrustLevel
    risk_type: RiskType


class SafeContextResponse(BaseModel):
    context_summary: str
    facts: list[str]
    high_trust_facts: list[str]
    low_trust_facts: list[str]
    warnings: list[str]
    sources: list[SafeContextSource]
