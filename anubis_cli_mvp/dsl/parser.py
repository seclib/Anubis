from __future__ import annotations

import shlex

from anubis_cli_mvp.models import Command


class CommandParser:
    """Basic slash-command parser for the MVP DSL."""

    def parse(self, text: str) -> Command:
        stripped = text.strip()
        if not stripped:
            return Command(name="")

        try:
            parts = shlex.split(stripped)
        except ValueError:
            parts = stripped.split()

        if not parts:
            return Command(name="")

        name = parts[0].lower()
        raw_args = stripped[len(parts[0]) :].strip()
        return Command(name=name, args=parts[1:], raw_args=raw_args)
