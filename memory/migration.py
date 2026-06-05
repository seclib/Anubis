from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from memory.schema import MemoryCollection, MemoryRecord, MemoryWriteResult, MigrationPlan
from memory.service import UnifiedMemoryService, memory_hash


class MemoryMigrationStrategy:
    """Non-destructive migration path from fragmented memory into Qdrant collections."""

    def __init__(self, service: UnifiedMemoryService) -> None:
        self.service = service

    def plan(self) -> MigrationPlan:
        return MigrationPlan(
            collections=(MemoryCollection.REPO, MemoryCollection.DOCS, MemoryCollection.CONVERSATIONS),
            sources=("repo memory", "obsidian memory", "conversation memory"),
            steps=(
                "Snapshot existing JSON/vector memory files before migration.",
                "Transform repository chunks into the repo collection.",
                "Transform Obsidian markdown notes into the docs collection.",
                "Transform conversation turns and agent messages into the conversations collection.",
                "Upsert through UnifiedMemoryService so content hashes deduplicate records.",
                "Run parity retrieval checks before disabling legacy retrieval paths.",
            ),
            safety_checks=(
                "Migration is append-only and does not delete legacy memory.",
                "Each record receives a deterministic content hash.",
                "Collections are lazy-created only when a source is migrated or queried.",
                "Rollback is switching callers back to legacy memory while Qdrant data remains isolated.",
            ),
        )

    def migrate_repo_memory(self, items: Iterable[dict[str, Any]]) -> MemoryWriteResult:
        records = []
        for index, item in enumerate(items):
            text = str(item.get("text") or item.get("content") or item.get("summary") or "").strip()
            if not text:
                continue
            source = str(item.get("source") or item.get("path") or f"repo:{index}")
            records.append(
                build_memory_record(
                    MemoryCollection.REPO,
                    text,
                    source=source,
                    metadata={**dict(item.get("metadata") or {}), "legacy_kind": item.get("kind", "repository")},
                    record_id=str(item.get("id") or ""),
                )
            )
        return self.service.store_records(records)

    def migrate_obsidian_notes(self, notes: Iterable[dict[str, Any] | Path]) -> MemoryWriteResult:
        records = []
        for index, note in enumerate(notes):
            if isinstance(note, Path):
                text = note.read_text(encoding="utf-8", errors="ignore")
                source = note.as_posix()
                metadata = {"legacy_kind": "obsidian_note", "title": note.stem}
                record_id = ""
            else:
                text = str(note.get("text") or note.get("content") or "").strip()
                source = str(note.get("source") or note.get("path") or note.get("note_path") or f"docs:{index}")
                metadata = {**dict(note.get("metadata") or {}), "legacy_kind": "obsidian_note", "title": note.get("title", "")}
                record_id = str(note.get("id") or "")
            if not text.strip():
                continue
            records.append(
                build_memory_record(
                    MemoryCollection.DOCS,
                    text,
                    source=source,
                    metadata=metadata,
                    record_id=record_id,
                )
            )
        return self.service.store_records(records)

    def migrate_conversation_memory(self, messages: Iterable[dict[str, Any]]) -> MemoryWriteResult:
        records = []
        for index, message in enumerate(messages):
            text = str(message.get("text") or message.get("content") or message.get("summary") or "").strip()
            if not text:
                continue
            role = str(message.get("role") or message.get("agent") or "conversation")
            source = str(message.get("source") or message.get("conversation_id") or f"conversation:{index}")
            records.append(
                build_memory_record(
                    MemoryCollection.CONVERSATIONS,
                    text,
                    source=source,
                    metadata={
                        **dict(message.get("metadata") or {}),
                        "legacy_kind": "conversation",
                        "role": role,
                    },
                    record_id=str(message.get("id") or ""),
                )
            )
        return self.service.store_records(records)


def build_memory_record(
    collection: MemoryCollection,
    text: str,
    *,
    source: str,
    metadata: dict[str, Any] | None = None,
    record_id: str = "",
) -> MemoryRecord:
    normalized = str(text).strip()
    content_hash = memory_hash(normalized)
    return MemoryRecord(
        id=record_id or f"{collection.value}:{content_hash[:24]}",
        collection=collection,
        text=normalized,
        source=str(source),
        metadata=dict(metadata or {}),
        content_hash=content_hash,
    )


__all__ = [
    "MemoryMigrationStrategy",
    "build_memory_record",
]
