from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import logging
from pathlib import Path
import threading
import time
from typing import Literal

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.core.config import settings
from rag.shared.backend_legacy.indexer import RagIndexer


logger = logging.getLogger("anubis.watcher")
SyncAction = Literal["upsert", "delete"]


@dataclass(frozen=True)
class SyncedFile:
    path: str
    hash: str
    chunks: int
    synced_at: float


class SyncState:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.project_root / "state" / "vault_sync_state.json"
        self._lock = threading.Lock()
        self._files = self._load()

    def unchanged(self, rel_path: str, digest: str) -> bool:
        with self._lock:
            return self._files.get(rel_path, {}).get("hash") == digest

    def mark_synced(self, rel_path: str, digest: str, chunks: int) -> None:
        with self._lock:
            self._files[rel_path] = asdict(
                SyncedFile(path=rel_path, hash=digest, chunks=chunks, synced_at=time.time())
            )
            self._save()

    def mark_deleted(self, rel_path: str) -> None:
        with self._lock:
            self._files.pop(rel_path, None)
            self._save()

    def _load(self) -> dict[str, dict[str, object]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        files = data.get("files", {}) if isinstance(data, dict) else {}
        return files if isinstance(files, dict) else {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "files": self._files}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


class VaultSync:
    """Incremental ingestion hook: Markdown file change -> vector memory update."""

    def __init__(self, indexer: RagIndexer | None = None, state: SyncState | None = None) -> None:
        self.indexer = indexer or RagIndexer()
        self.state = state or SyncState()

    def sync_path(self, raw_path: str | Path, action: SyncAction) -> None:
        path = Path(raw_path)
        if path.suffix != ".md":
            return
        try:
            rel_path = path.resolve().relative_to(settings.vault_path.resolve()).as_posix()
        except ValueError:
            logger.warning("ignored path outside vault path=%s", path)
            return

        if action == "delete" or not path.exists():
            self.indexer.delete_note(rel_path)
            self.state.mark_deleted(rel_path)
            logger.info("vault delete synced path=%s", rel_path)
            return

        content = path.read_bytes()
        digest = sha256(content).hexdigest()
        if self.state.unchanged(rel_path, digest):
            logger.info("vault sync skipped unchanged path=%s", rel_path)
            return
        chunks = self.indexer.index_note(rel_path)
        self.state.mark_synced(rel_path, digest, chunks)
        logger.info("vault upsert synced path=%s chunks=%s", rel_path, chunks)


class MarkdownChangeHandler(FileSystemEventHandler):
    def __init__(self, sync: VaultSync | None = None, debounce_seconds: float = 0.5) -> None:
        self.sync = sync or VaultSync()
        self.debounce_seconds = debounce_seconds
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_created(self, event) -> None:  # noqa: ANN001
        self._schedule(event.src_path, "upsert", event.is_directory)

    def on_modified(self, event) -> None:  # noqa: ANN001
        self._schedule(event.src_path, "upsert", event.is_directory)

    def on_deleted(self, event) -> None:  # noqa: ANN001
        self._schedule(event.src_path, "delete", event.is_directory)

    def on_moved(self, event) -> None:  # noqa: ANN001
        self._schedule(event.src_path, "delete", event.is_directory)
        self._schedule(event.dest_path, "upsert", event.is_directory)

    def _schedule(self, raw_path: str, action: SyncAction, is_directory: bool) -> None:
        if is_directory or not raw_path.endswith(".md"):
            return
        key = f"{action}:{raw_path}"
        with self._lock:
            timer = self._timers.pop(key, None)
            if timer:
                timer.cancel()
            timer = threading.Timer(self.debounce_seconds, self._sync, args=(raw_path, action))
            self._timers[key] = timer
            timer.daemon = True
            timer.start()

    def _sync(self, raw_path: str, action: SyncAction) -> None:
        with self._lock:
            self._timers.pop(f"{action}:{raw_path}", None)
        self.sync.sync_path(raw_path, action)


def start_observer(debounce_seconds: float = 0.5) -> Observer:
    settings.vault_path.mkdir(parents=True, exist_ok=True)
    observer = Observer()
    observer.schedule(
        MarkdownChangeHandler(debounce_seconds=debounce_seconds),
        str(settings.vault_path),
        recursive=True,
    )
    observer.start()
    logger.info("watching obsidian vault path=%s", settings.vault_path)
    return observer


def stop_observer(observer: Observer) -> None:
    observer.stop()
    observer.join()
    logger.info("stopped obsidian vault watcher")


def run(debounce_seconds: float = 0.5) -> None:
    observer = start_observer(debounce_seconds=debounce_seconds)
    try:
        while True:
            time.sleep(1)
    finally:
        stop_observer(observer)


if __name__ == "__main__":
    run()
