from __future__ import annotations

from time import perf_counter
from typing import Any

import structlog

from anubis_ai_core.models.orchestration import OrchestrationTraceEvent
from anubis_ai_core.observability.agent_trace import AgentTraceLogger

logger = structlog.get_logger(__name__)


class StageTimer:
    def __init__(self) -> None:
        self._started_at = perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return round((perf_counter() - self._started_at) * 1000, 3)


class OrchestrationTraceLogger:
    def __init__(self) -> None:
        self._sanitizer = AgentTraceLogger()

    def event(
        self,
        *,
        conversation_id: str,
        loop_iteration: int,
        stage: str,
        payload: dict[str, Any],
        latency_ms: float,
        errors: list[str] | None = None,
    ) -> OrchestrationTraceEvent:
        event = OrchestrationTraceEvent(
            conversation_id=conversation_id,
            loop_iteration=loop_iteration,
            stage=stage,  # type: ignore[arg-type]
            payload=self._sanitizer.sanitize(payload),
            latency_ms=latency_ms,
            errors=errors or [],
        )
        logger.info("multi_agent_stage", **event.model_dump(mode="json"))
        return event
