from __future__ import annotations

from time import perf_counter
from typing import Any

import structlog

from anubis_ai_core.models.agent import AgentState, AgentTraceEvent

logger = structlog.get_logger(__name__)

SENSITIVE_KEYS = {"api_key", "token", "secret", "password", "authorization"}


class StepTimer:
    def __init__(self) -> None:
        self._started_at = perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return round((perf_counter() - self._started_at) * 1000, 3)


class AgentTraceLogger:
    def snapshot_state(self, state: AgentState) -> dict[str, Any]:
        return {
            "conversation_id": state.conversation_id,
            "message_count": len(state.messages),
            "memory_context_count": len(state.memory_context),
            "tool_result_count": len(state.tool_results),
            "step_counter": state.step_counter,
            "termination_flag": state.termination_flag,
        }

    def sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else self.sanitize(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.sanitize(item) for item in value]
        if isinstance(value, str) and len(value) > 4000:
            return value[:4000] + "...[truncated]"
        return value

    def emit(self, event: AgentTraceEvent) -> None:
        logger.info("agent_step", **self.sanitize(event.model_dump(mode="json")))
