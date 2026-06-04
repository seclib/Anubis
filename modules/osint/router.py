from __future__ import annotations

from modules.osint.index import OsintModule
from modules.osint.schemas import AdapterExecution


class OsintRouter:
    def __init__(self, module: OsintModule | None = None) -> None:
        self.module = module or OsintModule()

    def route(self, target: str) -> AdapterExecution:
        return self.module.run(target)


__all__ = ["OsintRouter"]

