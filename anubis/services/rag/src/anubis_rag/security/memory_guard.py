from __future__ import annotations

from pydantic import BaseModel, Field

from anubis_rag.security.filter import SecurityFilter
from anubis_rag.security.models import SafeContextResponse


class MemoryWriteGuardDecision(BaseModel):
    should_write: bool
    reason: str
    risk_level: str
    requires_confirmation: bool
    candidate: str | None = Field(default=None, max_length=12000)


class MemoryWriteGuard:
    def __init__(self) -> None:
        self._filter = SecurityFilter()

    def evaluate(self, *, candidate: str, safe_context: SafeContextResponse, user_confirmed: bool = False) -> MemoryWriteGuardDecision:
        inspection = self._filter.inspect(candidate)
        if not inspection.safe:
            return MemoryWriteGuardDecision(
                should_write=False,
                reason="Candidate contains instruction-like or adversarial content.",
                risk_level="high",
                requires_confirmation=True,
                candidate=None,
            )
        if any(source.trust_level == "low" for source in safe_context.sources) and not user_confirmed:
            return MemoryWriteGuardDecision(
                should_write=False,
                reason="Candidate depends on low-trust retrieved context and needs user confirmation.",
                risk_level="medium",
                requires_confirmation=True,
                candidate=None,
            )
        if not user_confirmed:
            return MemoryWriteGuardDecision(
                should_write=False,
                reason="Memory writes from RAG context are disabled without explicit user confirmation.",
                risk_level="medium",
                requires_confirmation=True,
                candidate=None,
            )
        return MemoryWriteGuardDecision(
            should_write=True,
            reason="Candidate passed RAG security checks and was user-confirmed.",
            risk_level="low",
            requires_confirmation=False,
            candidate=candidate,
        )
