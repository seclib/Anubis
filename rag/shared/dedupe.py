from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar


T = TypeVar("T")


class SeenSet:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def add(self, key: object) -> bool:
        value = str(key)
        if value in self._seen:
            return False
        self._seen.add(value)
        return True

    def unique(self, items: Iterable[T], key: Callable[[T], object]) -> list[T]:
        output: list[T] = []
        for item in items:
            if self.add(key(item)):
                output.append(item)
        return output


def unique_by(items: Iterable[T], key: Callable[[T], object]) -> list[T]:
    seen = SeenSet()
    return seen.unique(items, key)
