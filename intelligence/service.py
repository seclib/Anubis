"""Lightweight intelligence extraction over retrieved or crawled text."""

from __future__ import annotations

import re
from typing import Any


IOC_PATTERN = re.compile(
    r"\b(?:CVE-\d{4}-\d{4,}|T\d{4}(?:\.\d{3})?|[a-fA-F0-9]{32,64}|(?:\d{1,3}\.){3}\d{1,3})\b"
)


class IntelligenceService:
    def analyze(self, text: str) -> dict[str, Any]:
        entities = list(dict.fromkeys(IOC_PATTERN.findall(text or "")))[:100]
        return {
            "entities": entities,
            "entity_count": len(entities),
            "has_cve": any(item.upper().startswith("CVE-") for item in entities),
            "has_mitre": any(item.upper().startswith("T") for item in entities),
        }


_SERVICE: IntelligenceService | None = None


def get_intelligence_service() -> IntelligenceService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = IntelligenceService()
    return _SERVICE


__all__ = ["IntelligenceService", "get_intelligence_service"]
