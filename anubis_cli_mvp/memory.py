from __future__ import annotations


class MemoryStore:
    """In-memory context store for the first CLI build."""

    def __init__(self) -> None:
        self._items: list[str] = []

    def save(self, data: str) -> str:
        self._items.append(data)
        return f"memory saved: {len(self._items)}"

    def query(self, text: str) -> list[str]:
        needle = text.lower()
        return [item for item in self._items if needle in item.lower()]

    def clear(self) -> str:
        count = len(self._items)
        self._items.clear()
        return f"memory cleared: {count}"
