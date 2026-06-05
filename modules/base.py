from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ModuleOption:
    name: str
    description: str
    required: bool = False
    default: str | None = None


class AnubisModule(Protocol):
    name: str
    domain: str
    aliases: tuple[str, ...]

    def info(self) -> dict[str, Any]:
        ...

    def options(self) -> list[ModuleOption]:
        ...

    def run(self, options: dict[str, str]) -> dict[str, Any]:
        ...
