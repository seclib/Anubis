from __future__ import annotations

import json

from anubis_ai_core.clients.llm import LlmClient
from anubis_ai_core.models.orchestration import CriticOutput, ExecutorOutput, PlannerOutput
from anubis_ai_core.orchestrator.json_agent import JsonAgent


class CriticAgent(JsonAgent[CriticOutput]):
    marker = "ANUBIS_CRITIC_JSON"
    model = CriticOutput

    def __init__(self, llm_client: LlmClient) -> None:
        super().__init__(llm_client)

    async def critique(self, *, user_input: str, plan: PlannerOutput, executor_output: ExecutorOutput) -> CriticOutput:
        prompt = (
            f"{self.marker}\n"
            "You are the Critic Agent. Evaluate correctness, completeness, safety, and groundedness.\n"
            "Return STRICT JSON only. No prose. No hidden reasoning.\n"
            "Approve only when the draft is complete enough to return to the user.\n"
            "JSON contract:\n"
            "{"
            "\"score\":0.0,"
            "\"approved\":false,"
            "\"issues\":[{\"type\":\"missing_info\",\"description\":\"...\",\"severity\":\"medium\"}],"
            "\"fix_instructions\":[\"...\"],"
            "\"final_response\":null"
            "}\n"
            f"INPUT_JSON:\n{json.dumps({'user_input': user_input, 'plan': plan.model_dump(mode='json'), 'executor_output': executor_output.model_dump(mode='json')}, ensure_ascii=True)}"
        )
        return await self.complete_json(prompt)
