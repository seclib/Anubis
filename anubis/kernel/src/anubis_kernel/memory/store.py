from __future__ import annotations

import asyncio
from collections import defaultdict


class InMemoryStore:
    def __init__(self) -> None:
        self._items: dict[str, list[str]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def store(self, conversation_id: str, content: str) -> None:
        async with self._lock:
            self._items[conversation_id].append(content)

    async def retrieve(self, conversation_id: str) -> list[str]:
        async with self._lock:
            return list(self._items[conversation_id])
