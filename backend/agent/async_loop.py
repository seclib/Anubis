from __future__ import annotations

import asyncio
from typing import Any

from backend.agent.loop import AgentLoop


class AsyncAgentLoop:
    """Async compatibility wrapper for the unified HTTP agent facade."""

    def __init__(self, loop: AgentLoop | None = None, max_rounds: int = 2) -> None:
        self.loop = loop or AgentLoop(max_iterations=max_rounds)
        self.max_rounds = max_rounds

    async def run(self, task: str) -> dict[str, Any]:
        result = await asyncio.to_thread(self.loop.chat, task)
        return {
            "task": task,
            "accepted": True,
            "answer": result.get("answer", ""),
            "memory_path": result.get("memory_path"),
            "history": [
                {
                    "round": 1,
                    "chunks_used": result.get("chunks_used", []),
                    "skills_used": result.get("skills_used", []),
                    "actions": result.get("actions", []),
                }
            ],
        }


__all__ = ["AsyncAgentLoop"]
