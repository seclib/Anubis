from __future__ import annotations

import json

from anubis_kernel.agent.schemas import AgentStep


class MockStepGenerator:
    async def next_step(self, *, user_input: str, step_index: int, tool_results: list[dict]) -> AgentStep:
        lowered = user_input.lower()
        if step_index == 0 and "search" in lowered:
            query = user_input.replace("search", "", 1).strip() or user_input
            return self._parse(
                {
                    "observation": "User asked for search-like retrieval.",
                    "reasoning_summary": "Call the controlled search tool once.",
                    "action_type": "tool_call",
                    "tool_call": {"tool_name": "web_search", "parameters": {"query": query}},
                    "final_output": None,
                    "confidence_score": 0.74,
                }
            )
        if step_index == 0 and "memory" in lowered:
            return self._parse(
                {
                    "observation": "User request references memory.",
                    "reasoning_summary": "Call the memory retrieval hook once.",
                    "action_type": "tool_call",
                    "tool_call": {"tool_name": "memory_retrieve", "parameters": {"query": user_input}},
                    "final_output": None,
                    "confidence_score": 0.72,
                }
            )
        if tool_results:
            summary = tool_results[-1].get("summary", "tool completed")
            final = f"Tool result: {summary}"
        else:
            final = f"Kernel response: {user_input}"
        return self._parse(
            {
                "observation": "Enough context is available to respond.",
                "reasoning_summary": "Return a bounded final answer.",
                "action_type": "respond",
                "tool_call": None,
                "final_output": final,
                "confidence_score": 0.93,
            }
        )

    def _parse(self, payload: dict) -> AgentStep:
        raw = json.dumps(payload)
        return AgentStep.model_validate_json(raw)
