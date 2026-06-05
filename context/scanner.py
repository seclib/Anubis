from __future__ import annotations

from pathlib import Path
from typing import Iterable

from anubis.context.schema import FileMetadata
from anubis.context.symbols import detect_language, extract_file_metadata


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
    ".jsx",
    ".json",
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


class RepositoryScanner:
    def __init__(self, root: Path | str, max_file_bytes: int = 300_000) -> None:
        self.root = Path(root).resolve()
        self.max_file_bytes = max_file_bytes

    def scan(self) -> tuple[FileMetadata, ...]:
        return tuple(self._iter_files())

    def _iter_files(self) -> Iterable[FileMetadata]:
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
            language = detect_language(path)
            symbols, imports, exports = extract_file_metadata(path, language)
            yield FileMetadata(
                path=str(relative),
                language=language,
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                symbols=tuple(symbols),
                imports=tuple(imports),
                exports=tuple(exports),
            )


__all__ = ["RepositoryScanner"]
