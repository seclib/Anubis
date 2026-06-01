"""Fast deterministic query analysis for cyber retrieval."""

from __future__ import annotations

import re
from typing import Any


DOMAIN_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("vulnerability", ("cve-", "cvss", "exploitability", "patch", "advisory")),
    ("mitre_attack", ("t1", "attack technique", "mitre", "att&ck")),
    ("detection_engineering", ("yara", "sigma", "snort", "suricata", "event id", "detection")),
    ("malware_research", ("malware", "ransomware", "loader", "stealer", "botnet", "ioc")),
    ("pentesting", ("pentest", "payload", "shell", "privilege escalation", "bypass", "exploit")),
    ("programming", ("python", "api", "github", "repository", "install", "library")),
    ("osint", ("osint", "whois", "shodan", "dork", "recon", "subdomain")),
)

EXPANSIONS: dict[str, list[str]] = {
    "credential dumping": ["T1003", "LSASS", "Mimikatz", "SAM", "NTDS.dit"],
    "ssrf": ["server-side request forgery", "IMDS", "169.254.169.254", "metadata service"],
    "web shell": ["China Chopper", "ASPXSpy", "PHP webshell", "persistence"],
    "yara": ["malware rule", "signature", "condition", "strings"],
    "sigma": ["detection rule", "SIEM", "logsource", "false positives"],
}


class QueryPlanner:
    def analyze(self, query: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = " ".join(str(query or "").split())
        lower = normalized.lower()
        domain = self._detect_domain(lower)
        expanded_terms = self._expand(lower)
        inferred_filters = dict(filters or {})
        if domain and "domain" not in inferred_filters:
            inferred_filters["domain"] = domain
        if "quality_score" not in inferred_filters:
            inferred_filters["quality_score"] = {"gte": 0.0}
        rewritten = normalized
        if expanded_terms:
            rewritten = f"{normalized} {' '.join(expanded_terms[:6])}"
        return {
            "original_query": normalized,
            "rewritten_query": rewritten,
            "expanded_terms": expanded_terms,
            "domain": domain or "general",
            "filters": inferred_filters,
            "entities": self._entities(normalized),
        }

    def _detect_domain(self, lower: str) -> str | None:
        if re.search(r"\bCVE-\d{4}-\d{4,}\b", lower, flags=re.I):
            return "vulnerability"
        if re.search(r"\bT\d{4}(?:\.\d{3})?\b", lower, flags=re.I):
            return "mitre_attack"
        for domain, markers in DOMAIN_PATTERNS:
            if any(marker in lower for marker in markers):
                return domain
        return None

    def _expand(self, lower: str) -> list[str]:
        terms: list[str] = []
        for key, values in EXPANSIONS.items():
            if key in lower:
                terms.extend(values)
        if "mimikatz" in lower and "credential dumping" not in lower:
            terms.extend(EXPANSIONS["credential dumping"][:3])
        return list(dict.fromkeys(terms))[:10]

    def _entities(self, query: str) -> list[str]:
        entities = re.findall(r"\b(?:CVE-\d{4}-\d{4,}|T\d{4}(?:\.\d{3})?|[A-Z][A-Za-z0-9_.-]{3,})\b", query)
        return list(dict.fromkeys(entities))[:20]


__all__ = ["QueryPlanner"]

