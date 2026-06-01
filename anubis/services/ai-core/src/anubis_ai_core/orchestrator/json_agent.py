from __future__ import annotations

import json
from typing import Generic, TypeVar

import structlog
from pydantic import BaseModel, ValidationError

from anubis_ai_core.clients.llm import LlmClient

ModelT = TypeVar("ModelT", bound=BaseModel)
logger = structlog.get_logger(__name__)


class JsonAgentError(RuntimeError):
    pass


class JsonAgent(Generic[ModelT]):
    marker: str
    model: type[ModelT]

    def __init__(self, llm_client: LlmClient, max_retries: int = 2) -> None:
        self._llm_client = llm_client
        self._max_retries = max_retries

    async def complete_json(self, prompt: str) -> ModelT:
        last_error: str | None = None
        for attempt in range(self._max_retries + 1):
            response = await self._llm_client.complete(prompt if attempt == 0 else self._retry_prompt(prompt, last_error))
            try:
                payload = self._parse_json(response.content)
                return self.model.model_validate(payload)
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)
                logger.warning("orchestration_json_validation_failed", marker=self.marker, attempt=attempt, error=last_error)
        raise JsonAgentError(f"{self.marker} failed strict JSON validation: {last_error}")

    def _retry_prompt(self, prompt: str, error: str | None) -> str:
        return (
            f"{prompt}\n\nPrevious output failed validation: {error}\n"
            "Return exactly one valid JSON object for this stage. No prose."
        )

    def _parse_json(self, content: str) -> dict:
        stripped = content.strip()
        if not stripped.startswith("{") or not stripped.endswith("}"):
            raise ValueError("Output must be one JSON object")
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise ValueError("Output JSON must be an object")
        return payload
