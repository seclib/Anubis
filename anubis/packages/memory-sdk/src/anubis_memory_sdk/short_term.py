from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import DefaultDict, Deque


@dataclass(frozen=True)
class MemoryEntry:
    role: str
    content: str


class ShortTermMemory:
    def __init__(self, max_messages: int = 24) -> None:
        self._max_messages = max_messages
        self._items: DefaultDict[str, Deque[MemoryEntry]] = defaultdict(lambda: deque(maxlen=max_messages))
        self._lock = asyncio.Lock()

    async def append(self, conversation_id: str, role: str, content: str) -> None:
        async with self._lock:
            self._items[conversation_id].append(MemoryEntry(role=role, content=content))

    async def list(self, conversation_id: str) -> list[MemoryEntry]:
        async with self._lock:
            return list(self._items[conversation_id])
