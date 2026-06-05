from __future__ import annotations

from typing import Any

from modules.base import ModuleOption
from modules.rag_client import ModuleRagClient


class Module:
    name = "bugbounty/technique"
    domain = "bugbounty"
    aliases = ("bugbounty", "bug", "bounty")

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "description": "Bug bounty reports, vulnerability patterns, payloads, and bypasses",
        }

    def options(self) -> list[ModuleOption]:
        return [
            ModuleOption("VULN", "Vulnerability type such as XSS, SSRF, IDOR, SQLi", required=True),
            ModuleOption("TARGET", "Program, asset, framework, or vulnerability target"),
        ]

    def run(self, options: dict[str, str]) -> dict[str, Any]:
        vuln = options["VULN"]
        target = options.get("TARGET", "")
        query = " ".join(part for part in (vuln, target) if part)
        filters = {"vulnerability_types": [vuln]}
        if target:
            filters["targets"] = [target]
        result = ModuleRagClient().investigate(self.domain, query, filters)
        result["module"] = self.name
        return result
