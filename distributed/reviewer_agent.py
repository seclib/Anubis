"""Distributed Reviewer Agent for ANUBIS Phase B4."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from anubis.distributed.rollback import (
    ReviewRecommendation,
    RollbackSignal,
    RollbackSignalCollector,
)
from anubis.distributed.validation_engine import ReviewInput, ReviewResult, ValidationEngine


class ReviewerAgent:
    """Validates execution results without executing tools or planning work."""

    def __init__(
        self,
        *,
        validation_engine: ValidationEngine | None = None,
        rollback_signals: RollbackSignalCollector | None = None,
    ) -> None:
        self.validation_engine = validation_engine or ValidationEngine()
        self.rollback_signals = rollback_signals or RollbackSignalCollector()

    def review(self, payload: ReviewInput | Mapping[str, Any]) -> ReviewResult:
        try:
            review_input = payload if isinstance(payload, ReviewInput) else ReviewInput.from_mapping(payload)
        except ValueError as exc:
            return ReviewResult(
                step_id=str(payload.get("step_id", "")) if isinstance(payload, Mapping) else "",
                valid=False,
                issues=(str(exc),),
                recommendation=ReviewRecommendation.RETRY,
            )

        result = self.validation_engine.validate(review_input)
        if result.recommendation == ReviewRecommendation.ROLLBACK:
            self.rollback_signals.emit(
                RollbackSignal(
                    step_id=result.step_id,
                    reason="; ".join(result.issues),
                    evidence={
                        "issues": list(result.issues),
                        "output": review_input.output,
                    },
                )
            )
        return result

    def review_dict(self, payload: ReviewInput | Mapping[str, Any]) -> dict[str, Any]:
        return self.review(payload).to_dict()


__all__ = ["ReviewerAgent"]
