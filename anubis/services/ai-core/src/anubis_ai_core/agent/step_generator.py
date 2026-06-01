from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import ValidationError

from anubis_ai_core.clients.llm import LlmClient
from anubis_ai_core.models.agent import AgentState, AgentStep

logger = structlog.get_logger(__name__)


class AgentStepGenerationError(RuntimeError):
    pass


class AgentStepGenerator:
    def __init__(self, llm_client: LlmClient, max_retries: int = 2) -> None:
        self._llm_client = llm_client
        self._max_retries = max_retries

    async def generate(self, state: AgentState) -> AgentStep:
        prompt = self._build_prompt(state)
        last_error: str | None = None
        for attempt in range(self._max_retries + 1):
            response = await self._llm_client.complete(prompt if attempt == 0 else self._retry_prompt(prompt, last_error))
            try:
                payload = self._parse_json_object(response.content)
                return AgentStep.model_validate(payload)
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)
                logger.warning("agent_step_validation_failed", attempt=attempt, error=last_error)
        raise AgentStepGenerationError(f"LLM did not produce a valid AgentStep: {last_error}")

    def _build_prompt(self, state: AgentState) -> str:
        recent_messages = [message.model_dump(mode="json") for message in state.messages[-8:]]
        memory_context = [memory.model_dump(mode="json") for memory in state.memory_context[-8:]]
        tool_results = [result.model_dump(mode="json") for result in state.tool_results[-8:]]
        state_payload: dict[str, Any] = {
            "conversation_id": state.conversation_id,
            "messages": recent_messages,
            "memory_context": memory_context,
            "tool_results": tool_results,
            "step_counter": state.step_counter,
            "termination_flag": state.termination_flag,
        }
        return (
            "ANUBIS_AGENT_STEP_JSON\n"
            "You are only a deterministic step generator for an explicit agent loop.\n"
            "Return STRICT JSON only. No markdown. No extra text. No hidden reasoning.\n"
            "Allowed action_type values: tool_call, retrieve_memory, respond, store_memory.\n"
            "Allowed tool_name values: web_search, rag_query, file_read, file_write, memory_store, memory_retrieve.\n"
            "Use reasoning_summary as a short observable summary, not chain-of-thought.\n"
            "If memory is needed, choose retrieve_memory. If durable memory should be stored, choose store_memory.\n"
            "If enough information exists, choose respond.\n"
            "JSON contract:\n"
            "{"
            "\"observation\":\"...\","
            "\"reasoning_summary\":\"...\","
            "\"action_type\":\"tool_call|retrieve_memory|respond|store_memory\","
            "\"tool_call\":{\"tool_name\":\"...\",\"input_schema\":{},\"parameters\":{},\"async_flag\":false},"
            "\"final_output\":\"...\","
            "\"confidence_score\":0.0"
            "}\n"
            f"STATE_JSON:\n{json.dumps(state_payload, ensure_ascii=True)}"
        )

    def _retry_prompt(self, prompt: str, error: str | None) -> str:
        return (
            f"{prompt}\n\nYour previous output was invalid JSON or failed schema validation: {error}.\n"
            "Return exactly one JSON object matching the contract."
        )

    def _parse_json_object(self, content: str) -> dict[str, Any]:
        stripped = content.strip()
        if not stripped.startswith("{") or not stripped.endswith("}"):
            raise ValueError("Output must be a single JSON object")
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise ValueError("Output JSON must be an object")
        return payload
