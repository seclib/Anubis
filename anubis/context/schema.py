from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FileMetadata:
    path: str
    language: str
    size_bytes: int
    mtime_ns: int
    symbols: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodeChunk:
    id: str
    file_path: str
    language: str
    content: str
    start_line: int
    end_line: int
    symbols: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddedChunk:
    chunk: CodeChunk
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class RepositoryIndex:
    root: str
    files: tuple[FileMetadata, ...]
    chunks: tuple[EmbeddedChunk, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievedContext:
    chunk: CodeChunk
    score: float
    semantic_score: float
    keyword_score: float
    file_importance: float
    symbol_score: float


@dataclass(frozen=True)
class BuiltContext:
    task: str
    context_chunks: list[dict[str, Any]]
    summary: str


__all__ = [
    "BuiltContext",
    "CodeChunk",
    "EmbeddedChunk",
    "FileMetadata",
    "RepositoryIndex",
    "RetrievedContext",
]
