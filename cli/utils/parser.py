from __future__ import annotations

import shlex
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: list[str] = field(default_factory=list)
    raw_args: str = ""


class CommandParser:
    def parse(self, text: str) -> ParsedCommand:
        stripped = text.strip()
        if not stripped:
            return ParsedCommand("")
        try:
            parts = shlex.split(stripped)
        except ValueError:
            parts = stripped.split()
        if not parts:
            return ParsedCommand("")
        name = parts[0].lower()
        if not name.startswith("/"):
            name = f"/{name}"
        return ParsedCommand(name=name, args=parts[1:], raw_args=stripped[len(parts[0]) :].strip())
