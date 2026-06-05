from __future__ import annotations

from typing import Any

from modules.base import ModuleOption
from modules.rag_client import ModuleRagClient


class Module:
    name = "osint/recon"
    domain = "osint"
    aliases = ("osint", "recon")

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "description": "OSINT entity, domain, IP, email, username, and leak intelligence",
        }

    def options(self) -> list[ModuleOption]:
        return [
            ModuleOption("TARGET", "Domain, IP, email, username, or organization", required=True),
            ModuleOption("SOURCE", "Optional OSINT source filter"),
        ]

    def run(self, options: dict[str, str]) -> dict[str, Any]:
        target = options["TARGET"]
        source = options.get("SOURCE", "")
        query = " ".join(part for part in (target, source) if part)
        filters = {"targets": [target]}
        result = ModuleRagClient().investigate(self.domain, query, filters)
        result["module"] = self.name
        return result
