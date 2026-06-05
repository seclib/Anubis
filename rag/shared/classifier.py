from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.shared.config import DOMAINS


CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.I)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DOMAIN_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.I)
EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
HASH_RE = re.compile(r"\b[a-f0-9]{32,64}\b", re.I)
MITRE_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.I)
PATH_RE = re.compile(r"(?:^|\s)(?:[\w.-]+/)+[\w.-]+\.(?:py|ts|tsx|js|go|rs|java|md|json|yaml|yml)\b")


KEYWORDS: dict[str, set[str]] = {
    "osint": {
        "domain", "ip", "asn", "whois", "rdap", "subdomain", "dns", "leak",
        "paste", "breach", "metadata", "infrastructure", "attribution", "pivot",
    },
    "cve": {
        "cve", "cvss", "epss", "kev", "nvd", "mitre", "advisory", "patch",
        "affected", "vulnerable", "exploitability", "vendor", "product",
    },
    "bugbounty": {
        "bug bounty", "hackerone", "bugcrowd", "intigriti", "idor", "ssrf",
        "xss", "csrf", "payload", "reproduce", "impact", "bypass", "poc",
    },
    "dev": {
        "code", "function", "class", "repo", "github", "stack trace", "api",
        "dependency", "package", "fix", "refactor", "test", "implementation",
    },
    "cyberdefense": {
        "detect", "detection", "sigma", "yara", "suricata", "splunk", "kql",
        "siem", "edr", "hunt", "incident", "containment", "mitre", "attack",
    },
}


INTENT_KEYWORDS: dict[str, set[str]] = {
    "lookup": {"what is", "tell me", "lookup", "summarize", "explain"},
    "correlate": {"correlate", "related", "connected", "associated", "pivot"},
    "exploitability": {"exploited", "exploitability", "in the wild", "kev", "epss"},
    "detection": {"detect", "hunt", "sigma", "splunk", "kql", "yara", "rule"},
    "remediation": {"fix", "patch", "mitigate", "upgrade", "remediate"},
    "recon": {"recon", "whois", "subdomain", "attack surface", "osint"},
}


@dataclass
class Classification:
    query: str
    intent: str
    entities: dict[str, list[str]] = field(default_factory=dict)
    rule_scores: dict[str, float] = field(default_factory=dict)
    entity_scores: dict[str, float] = field(default_factory=dict)


class QueryClassifier:
    def classify(self, query: str) -> Classification:
        normalized = " ".join(query.strip().split())
        lowered = normalized.lower()
        entities = self.extract_entities(normalized)
        intent = self.detect_intent(lowered)
        rule_scores = self.score_rules(lowered)
        entity_scores = self.score_entities(entities)
        return Classification(
            query=normalized,
            intent=intent,
            entities=entities,
            rule_scores=rule_scores,
            entity_scores=entity_scores,
        )

    def extract_entities(self, query: str) -> dict[str, list[str]]:
        return {
            "cves": sorted(set(match.upper() for match in CVE_RE.findall(query))),
            "ips": sorted(set(IP_RE.findall(query))),
            "domains": sorted(set(match.lower() for match in DOMAIN_RE.findall(query))),
            "emails": sorted(set(match.lower() for match in EMAIL_RE.findall(query))),
            "hashes": sorted(set(match.lower() for match in HASH_RE.findall(query))),
            "mitre_techniques": sorted(set(match.upper() for match in MITRE_RE.findall(query))),
            "paths": sorted(set(match.strip() for match in PATH_RE.findall(query))),
        }

    def detect_intent(self, lowered: str) -> str:
        scores = {intent: 0 for intent in INTENT_KEYWORDS}
        for intent, terms in INTENT_KEYWORDS.items():
            scores[intent] = sum(1 for term in terms if term in lowered)
        best_intent, best_score = max(scores.items(), key=lambda item: item[1])
        return best_intent if best_score else "lookup"

    def score_rules(self, lowered: str) -> dict[str, float]:
        scores = {domain: 0.0 for domain in DOMAINS}
        for domain, terms in KEYWORDS.items():
            hits = sum(1 for term in terms if term in lowered)
            scores[domain] = min(1.0, hits / 4.0)
        return scores

    def score_entities(self, entities: dict[str, list[str]]) -> dict[str, float]:
        scores = {domain: 0.0 for domain in DOMAINS}
        if entities["cves"]:
            scores["cve"] = 1.0
            scores["cyberdefense"] = max(scores["cyberdefense"], 0.35)
        if entities["ips"] or entities["domains"] or entities["emails"] or entities["hashes"]:
            scores["osint"] = 1.0
        if entities["mitre_techniques"]:
            scores["cyberdefense"] = 1.0
        if entities["paths"]:
            scores["dev"] = 1.0
        return scores
