from __future__ import annotations

from modules.osint.adapter import OsintSkillAdapter
from modules.osint.schemas import AdapterExecution, OsintInput


class OsintModule:
    """Native Anubis facade for the external osint-skill repository."""

    def __init__(self, adapter: OsintSkillAdapter | None = None) -> None:
        self.adapter = adapter or OsintSkillAdapter()

    def run(self, target: str, context: str = "") -> AdapterExecution:
        return self.adapter.execute(OsintInput(target=target, context=context))


def run_osint(target: str, context: str = "") -> AdapterExecution:
    return OsintModule().run(target, context=context)


__all__ = ["OsintModule", "run_osint"]

