from __future__ import annotations

from anubis_ai_core.agent.tool_dispatcher import ToolDispatcher
from anubis_ai_core.memory.interface import AgentMemoryInterface
from anubis_ai_core.models.agent import AgentMessage, AgentState, AgentStep, MemoryContextItem, ToolCall


class AgentStepExecutor:
    def __init__(self, *, dispatcher: ToolDispatcher, memory: AgentMemoryInterface) -> None:
        self._dispatcher = dispatcher
        self._memory = memory

    async def execute(self, state: AgentState, step: AgentStep, request_id: str) -> AgentState:
        next_state = state.model_copy(deep=True)
        next_state.step_counter += 1

        if step.action_type == "respond":
            next_state.messages.append(AgentMessage(role="assistant", content=step.final_output or ""))
            next_state.termination_flag = True
            return next_state

        if step.action_type == "retrieve_memory":
            query = self._query_from_step(next_state, step)
            result = await self._dispatcher.dispatch(ToolCall(tool_name="memory_retrieve", parameters={"query": query, "limit": 5}))
            next_state.tool_results.append(result)
            if result.status == "succeeded":
                for item in result.output.get("memories", []):
                    next_state.memory_context.append(MemoryContextItem.model_validate(item))
            return next_state

        if step.action_type == "store_memory":
            assert step.tool_call is not None
            store_call = step.tool_call.model_copy(update={"tool_name": "memory_store"})
            next_state.tool_results.append(await self._dispatcher.dispatch(store_call))
            return next_state

        if step.action_type == "tool_call":
            assert step.tool_call is not None
            result = await self._dispatcher.dispatch(step.tool_call)
            next_state.tool_results.append(result)
            if step.tool_call.tool_name in {"rag_query", "memory_retrieve"} and result.status == "succeeded":
                for item in result.output.get("memories", []):
                    next_state.memory_context.append(MemoryContextItem.model_validate(item))
            return next_state

        return next_state

    def _query_from_step(self, state: AgentState, step: AgentStep) -> str:
        if step.tool_call and "query" in step.tool_call.parameters:
            return str(step.tool_call.parameters["query"])
        for message in reversed(state.messages):
            if message.role == "user":
                return message.content
        return step.observation
