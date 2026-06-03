from __future__ import annotations

from typing import Protocol

from anubis.context.schema import BuiltContext, RepositoryIndex, RetrievedContext
from anubis.types import AgentContext, ContextChunk, JSONObject, TaskSnapshot


class ContextIndexer(Protocol):
    def index_repository(self) -> RepositoryIndex:
        ...


class ContextRetriever(Protocol):
    def retrieve(self, index: RepositoryIndex, task: str, top_k: int) -> tuple[RetrievedContext, ...]:
        ...


class ContextCompressor(Protocol):
    def compress(self, task: str, chunks: tuple[RetrievedContext, ...]) -> tuple[list[dict[str, object]], str]:
        ...


class ContextEngine(Protocol):
    def build(self, task: str, top_k: int) -> BuiltContext:
        ...


__all__ = [
    "ContextCompressor",
    "ContextEngine",
    "ContextIndexer",
    "ContextRetriever",
]
