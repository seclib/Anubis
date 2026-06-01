"""Priority URL frontier."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field


@dataclass(order=True)
class FrontierItem:
    sort_priority: float
    url: str = field(compare=False)
    depth: int = field(compare=False, default=0)
    discovered_from: str = field(compare=False, default="")


class URLFrontier:
    def __init__(self) -> None:
        self._heap: list[FrontierItem] = []

    def push(self, url: str, priority: float, depth: int = 0, discovered_from: str = "") -> None:
        heapq.heappush(self._heap, FrontierItem(sort_priority=-priority, url=url, depth=depth, discovered_from=discovered_from))

    def pop(self) -> FrontierItem | None:
        if not self._heap:
            return None
        return heapq.heappop(self._heap)

    def __len__(self) -> int:
        return len(self._heap)


__all__ = ["FrontierItem", "URLFrontier"]

