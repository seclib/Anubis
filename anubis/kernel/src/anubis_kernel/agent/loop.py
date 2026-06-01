from __future__ import annotations

from uuid import uuid4

from anubis_kernel.agent.llm import MockStepGenerator
from anubis_kernel.agent.schemas import AgentRunRequest, AgentRunResponse, AgentStep, MemoryDecision
from anubis_kernel.memory.store import InMemoryStore
from anubis_kernel.tools.dispatcher import ToolDispatcher


class AgentLoop:
    def __init__(self, *, dispatcher: ToolDispatcher, memory: InMemoryStore) -> None:
        self._dispatcher = dispatcher
        self._memory = memory
        self._step_generator = MockStepGenerator()

    async def run(self, request: AgentRunRequest) -> AgentRunResponse:
        conversation_id = request.conversation_id or str(uuid4())
        steps: list[AgentStep] = []
        tool_results: list[dict] = []
        final_output = ""

        for step_index in range(request.max_steps):
            step = await self._step_generator.next_step(
                user_input=request.input,
                step_index=step_index,
                tool_results=tool_results,
            )
            steps.append(step)

            if step.action_type == "tool_call" and step.tool_call:
                result = await self._dispatcher.dispatch(step.tool_call)
                tool_results.append(result)
                continue

            if step.action_type == "respond":
                final_output = step.final_output or ""
                break

        if not final_output:
            final_output = "Kernel stopped at max_steps without final response."

        memory_decision = self._memory_decision(request.input)
        if memory_decision.should_store:
            await self._memory.store(conversation_id, request.input)

        return AgentRunResponse(
            conversation_id=conversation_id,
            final_output=final_output,
            memory_decision=memory_decision,
            steps=steps,
            tool_results=tool_results,
        )

    def _memory_decision(self, user_input: str) -> MemoryDecision:
        lowered = user_input.lower()
        if "remember" in lowered or "preference" in lowered:
            return MemoryDecision(should_store=True, reason="Durable memory marker found.")
        return MemoryDecision(should_store=False, reason="No durable memory marker found.")
