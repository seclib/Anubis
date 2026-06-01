"""Obsidian vault scanner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from memory import hermes, vector

MAX_NOTE_BYTES = 512_000
SKIP_DIRS = {".obsidian", ".trash", ".git"}


@dataclass(frozen=True)
class VaultNote:
    path: Path
    relative_path: str
    text: str
    content_hash: str
    size: int
    mtime: float


class VaultScanner:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or hermes.obsidian_vault_path(create=True)

    def scan(self, *, limit: int | None = None) -> list[VaultNote]:
        notes: list[VaultNote] = []
        for path in sorted(self.root.rglob("*.md")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if not path.is_file() or stat.st_size <= 0 or stat.st_size > MAX_NOTE_BYTES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if not text.strip():
                continue
            relative = path.relative_to(self.root).as_posix()
            notes.append(
                VaultNote(
                    path=path,
                    relative_path=relative,
                    text=text,
                    content_hash=vector._content_hash(text),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
            )
            if limit is not None and len(notes) >= max(0, int(limit)):
                break
        return notes


__all__ = ["VaultNote", "VaultScanner"]

