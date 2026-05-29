"""Stateless LLM-backed agent caller adapter."""

from __future__ import annotations

from core.contracts import AgentPromptBuilder, AgentSpecGetter
from llm.ollama import call_llm


class LLMAgentCaller:
    """Connect injected agent metadata to an injected/stateless LLM client."""

    def __init__(
        self,
        *,
        get_agent: AgentSpecGetter,
        build_prompt: AgentPromptBuilder,
        llm_client=call_llm,
    ) -> None:
        self._get_agent = get_agent
        self._build_prompt = build_prompt
        self._llm_client = llm_client

    def __call__(self, agent_name: str, task_prompt: str, collaboration_context: str = "") -> str:
        spec = self._get_agent(agent_name)
        prompt = self._build_prompt(agent_name, task_prompt, collaboration_context)
        return self._llm_client(prompt, model=spec.model)


def build_llm_agent_caller(
    *,
    get_agent: AgentSpecGetter,
    build_prompt: AgentPromptBuilder,
    llm_client=call_llm,
) -> LLMAgentCaller:
    return LLMAgentCaller(
        get_agent=get_agent,
        build_prompt=build_prompt,
        llm_client=llm_client,
    )


__all__ = ["LLMAgentCaller", "build_llm_agent_caller"]
