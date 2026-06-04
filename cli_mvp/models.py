from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Command:
    name: str
    args: list[str] = field(default_factory=list)
    raw_args: str = ""


@dataclass(frozen=True)
class RenderBlock:
    task: str
    result: str
    status: dict[str, str] | None = None
