from __future__ import annotations

from typing import Any

from modules.base import ModuleOption
from modules.rag_client import ModuleRagClient


class Module:
    name = "defense/detect"
    domain = "cyberdefense"
    aliases = ("defense", "blue", "cyberdefense")

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "description": "MITRE ATT&CK, IDS rules, detections, mitigations, and playbooks",
        }

    def options(self) -> list[ModuleOption]:
        return [
            ModuleOption("TECHNIQUE", "MITRE technique, behavior, alert, or defense query", required=True),
            ModuleOption("LOG_SOURCE", "Optional telemetry source"),
        ]

    def run(self, options: dict[str, str]) -> dict[str, Any]:
        technique = options["TECHNIQUE"]
        log_source = options.get("LOG_SOURCE", "")
        query = " ".join(part for part in (technique, log_source) if part)
        filters = {"mitre_techniques": [technique]}
        if log_source:
            filters["log_source"] = [log_source]
        result = ModuleRagClient().investigate(self.domain, query, filters)
        result["module"] = self.name
        return result
