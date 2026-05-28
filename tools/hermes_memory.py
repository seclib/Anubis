"""Tool wrappers for Hermes long-term memory."""

from __future__ import annotations

from typing import Any

from agent.hermes_memory import (
    append_daily_memory_summary as _append_daily_memory_summary,
    hermes_recall as _hermes_recall,
    index_obsidian_vault as _index_obsidian_vault,
    store_hermes_memory as _store_hermes_memory,
    write_obsidian_note as _write_obsidian_note,
)


def search_hermes_memory(query: str, top_k: int = 5) -> dict[str, Any]:
    return _hermes_recall(query=query, top_k=top_k)


def index_obsidian_vault(force: bool = False) -> dict[str, Any]:
    return _index_obsidian_vault(force=force)


def store_hermes_memory(
    summary: str,
    task: str = "",
    result: str = "",
    lessons: list[str] | None = None,
    tags: list[str] | None = None,
    write_note: bool = True,
) -> dict[str, Any]:
    return _store_hermes_memory(
        summary=summary,
        task=task,
        result=result,
        lessons=lessons,
        tags=tags,
        write_note=write_note,
    )


def write_obsidian_note(title: str, content: str, folder: str = "Hermes") -> dict[str, Any]:
    return _write_obsidian_note(title=title, content=content, folder=folder)


def append_daily_memory_summary(entry: dict[str, Any], day: str | None = None) -> dict[str, Any]:
    return _append_daily_memory_summary(entry=entry, day=day)


__all__ = [
    "index_obsidian_vault",
    "append_daily_memory_summary",
    "search_hermes_memory",
    "store_hermes_memory",
    "write_obsidian_note",
]
