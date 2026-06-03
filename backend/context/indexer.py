from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Iterable

from backend.core.config import settings
from backend.core.paths import ensure_inside


DEFAULT_INDEX_PATH = Path("state/repo_context_index.jsonl")
EMBEDDING_DIMENSIONS = 64
MAX_FILE_BYTES = 250_000
CHUNK_CHARS = 2200
CHUNK_OVERLAP = 250

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
}

TEXT_SUFFIXES = {
    ".css",
    ".go",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".rs",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class RepoChunk:
    path: str
    chunk_id: int
    start: int
    end: int
    text: str
    embedding: list[float]
    mtime_ns: int
    size: int


@dataclass(frozen=True)
class IndexStats:
    files_indexed: int
    chunks_indexed: int
    index_path: str


class RepositoryIndexer:
    def __init__(
        self,
        root: Path | None = None,
        index_path: Path | None = None,
        *,
        max_file_bytes: int = MAX_FILE_BYTES,
    ) -> None:
        self.root = (root or settings.project_root).resolve()
        raw_index_path = index_path or DEFAULT_INDEX_PATH
        self.index_path = ensure_inside(self.root, raw_index_path)
        self.max_file_bytes = max_file_bytes

    def index(self) -> IndexStats:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        files_indexed = 0
        chunks_indexed = 0
        with self.index_path.open("w", encoding="utf-8") as handle:
            for path in self.iter_files():
                file_chunks = 0
                for chunk in self.iter_chunks(path):
                    handle.write(json.dumps(asdict(chunk), ensure_ascii=False, separators=(",", ":")) + "\n")
                    file_chunks += 1
                if file_chunks:
                    files_indexed += 1
                    chunks_indexed += file_chunks
        return IndexStats(files_indexed, chunks_indexed, str(self.index_path))

    def ensure_index(self) -> IndexStats | None:
        if self.index_path.exists() and self.index_path.stat().st_size > 0:
            index_mtime = self.index_path.stat().st_mtime_ns
            if not any(path.stat().st_mtime_ns > index_mtime for path in self.iter_files()):
                return None
            return self.index()
        return self.index()

    def is_stale(self) -> bool:
        if not self.index_path.exists() or self.index_path.stat().st_size <= 0:
            return True
        index_mtime = self.index_path.stat().st_mtime_ns
        return any(path.stat().st_mtime_ns > index_mtime for path in self.iter_files())

    def iter_files(self) -> Iterable[Path]:
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root)
            if any(part in IGNORED_DIRS for part in relative.parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size <= 0 or stat.st_size > self.max_file_bytes:
                continue
            yield path

    def iter_chunks(self, path: Path) -> Iterable[RepoChunk]:
        try:
            stat = path.stat()
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return
        if not text.strip():
            return

        relative = str(path.relative_to(self.root))
        chunk_id = 0
        start = 0
        text_length = len(text)
        while start < text_length:
            end = min(text_length, start + CHUNK_CHARS)
            chunk_text = text[start:end].strip()
            if chunk_text:
                yield RepoChunk(
                    path=relative,
                    chunk_id=chunk_id,
                    start=start,
                    end=end,
                    text=chunk_text,
                    embedding=embed_text(f"{relative}\n{chunk_text}"),
                    mtime_ns=stat.st_mtime_ns,
                    size=stat.st_size,
                )
                chunk_id += 1
            if end >= text_length:
                break
            start = max(end - CHUNK_OVERLAP, start + 1)


def embed_text(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        bucket = int.from_bytes(digest, "big") % dimensions
        vector[bucket] += 1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [round(value / magnitude, 6) for value in vector]


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_/-]{2,}", text.lower())


__all__ = [
    "DEFAULT_INDEX_PATH",
    "IndexStats",
    "RepositoryIndexer",
    "RepoChunk",
    "embed_text",
    "tokenize",
]
