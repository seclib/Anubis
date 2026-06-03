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


@dataclass(frozen=True)
class ContextBudget:
    max_tokens: int = 2500
    max_files: int = 5
    min_files: int = 3
    max_chunks_per_file: int = 2
    reserved_memory_tokens: int = 300

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextBuildRequest:
    task: str
    repo_state: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    budget: ContextBudget = field(default_factory=ContextBudget)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RankedFile:
    path: str
    score: float
    reason: str
    chunks: tuple[dict[str, Any], ...] = ()
    estimated_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MinimalContext:
    task: str
    files: tuple[RankedFile, ...]
    memory: tuple[dict[str, Any], ...]
    context: str
    estimated_tokens: int
    token_budget: int
    omitted_files: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "BuiltContext",
    "CodeChunk",
    "ContextBudget",
    "ContextBuildRequest",
    "EmbeddedChunk",
    "FileMetadata",
    "MinimalContext",
    "RankedFile",
    "RepositoryIndex",
    "RetrievedContext",
]
