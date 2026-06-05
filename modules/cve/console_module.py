from __future__ import annotations

from typing import Any

from modules.base import ModuleOption
from modules.rag_client import ModuleRagClient


class Module:
    name = "cve/analyze"
    domain = "cve"
    aliases = ("cve", "vuln", "vulnerability")

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "description": "CVE, NVD, MITRE, KEV, exploitability, and patch intelligence",
        }

    def options(self) -> list[ModuleOption]:
        return [
            ModuleOption("CVE", "CVE identifier or vulnerability query", required=True),
            ModuleOption("PRODUCT", "Affected product or vendor filter"),
        ]

    def run(self, options: dict[str, str]) -> dict[str, Any]:
        cve = options["CVE"]
        product = options.get("PRODUCT", "")
        query = " ".join(part for part in (cve, product) if part)
        filters = {"cves": [cve]}
        if product:
            filters["products"] = [product]
        result = ModuleRagClient().investigate(self.domain, query, filters)
        result["module"] = self.name
        return result
