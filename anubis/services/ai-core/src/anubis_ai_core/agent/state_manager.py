from __future__ import annotations

import asyncio

from anubis_ai_core.models.agent import AgentMessage, AgentState


class AgentStateManager:
    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, conversation_id: str | None, user_input: str) -> AgentState:
        async with self._lock:
            if conversation_id and conversation_id in self._states:
                state = self._states[conversation_id].model_copy(deep=True)
            else:
                state = AgentState(conversation_id=conversation_id) if conversation_id else AgentState()
            state.messages.append(AgentMessage(role="user", content=user_input))
            return state

    async def save(self, state: AgentState) -> None:
        async with self._lock:
            self._states[state.conversation_id] = state.model_copy(deep=True)
