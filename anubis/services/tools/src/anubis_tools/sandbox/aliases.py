from __future__ import annotations

TOOL_ALIASES = {
    "web_search": "web.search",
    "rag_query": "memory.retrieve",
    "file_read": "file.read",
    "file_write": "note.write",
    "memory_retrieve": "memory.retrieve",
}


def canonical_tool_name(tool_name: str) -> str:
    return TOOL_ALIASES.get(tool_name, tool_name)
