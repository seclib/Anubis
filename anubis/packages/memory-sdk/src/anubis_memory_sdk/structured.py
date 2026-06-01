from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class StructuredMemory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    namespace: str
    payload: dict[str, Any]


class StructuredMemoryStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "structured-memory.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def append(self, memory: StructuredMemory) -> None:
        async with self._lock:
            await asyncio.to_thread(self._append_sync, memory)

    async def list(self, namespace: str) -> list[StructuredMemory]:
        async with self._lock:
            if not self._path.exists():
                return []
            lines = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
            memories: list[StructuredMemory] = []
            for line in lines.splitlines():
                if not line.strip():
                    continue
                data = json.loads(line)
                item = StructuredMemory.model_validate(data)
                if item.namespace == namespace:
                    memories.append(item)
            return memories

    def _append_sync(self, memory: StructuredMemory) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(memory.model_dump_json() + "\n")
