from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from anubis_ai_core.models.orchestration import OrchestrationSession


class OrchestrationSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, OrchestrationSession] = {}
        self._lock = asyncio.Lock()

    async def start(self, conversation_id: str | None, user_input: str) -> OrchestrationSession:
        async with self._lock:
            if conversation_id and conversation_id in self._sessions:
                session = self._sessions[conversation_id].model_copy(
                    update={"user_input": user_input, "updated_at": datetime.now(UTC)}
                )
            else:
                session = (
                    OrchestrationSession(conversation_id=conversation_id, user_input=user_input)
                    if conversation_id
                    else OrchestrationSession(user_input=user_input)
                )
            self._sessions[session.conversation_id] = session
            return session
