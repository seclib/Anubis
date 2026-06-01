from __future__ import annotations

import json

from anubis_ai_core.clients.llm import LlmClient
from anubis_ai_core.models.orchestration import PlannerOutput
from anubis_ai_core.orchestrator.json_agent import JsonAgent


class PlannerAgent(JsonAgent[PlannerOutput]):
    marker = "ANUBIS_PLANNER_JSON"
    model = PlannerOutput

    def __init__(self, llm_client: LlmClient) -> None:
        super().__init__(llm_client)

    async def plan(self, user_input: str, memory_hint: str | None = None) -> PlannerOutput:
        prompt = (
            f"{self.marker}\n"
            "You are the Planner Agent in a deterministic multi-agent pipeline.\n"
            "Return STRICT JSON only. No prose. No hidden reasoning.\n"
            "Plan subtasks, dependencies, execution_order, risk_notes, and confidence.\n"
            "Allowed tool_name values: web_search, rag_query, file_read, file_write, memory_retrieve.\n"
            "Memory must never be auto-written.\n"
            "JSON contract:\n"
            "{"
            "\"goal\":\"...\","
            "\"subtasks\":[{\"id\":1,\"task\":\"...\",\"tool_needed\":false,\"tool_name\":null,\"dependencies\":[]}],"
            "\"execution_order\":[1],"
            "\"risk_notes\":\"...\","
            "\"confidence\":0.0"
            "}\n"
            f"INPUT_JSON:\n{json.dumps({'user_input': user_input, 'memory_hint': memory_hint}, ensure_ascii=True)}"
        )
        return await self.complete_json(prompt)
