from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rag.shared.classifier import QueryClassifier
from rag.shared.config import DOMAINS, config


SEMANTIC_PROTOTYPES: dict[str, tuple[str, ...]] = {
    "osint": (
        "investigate domains ips emails hashes infrastructure leaks attribution",
        "map attack surface using public sources and metadata",
    ),
    "cve": (
        "analyze cve cvss epss kev affected versions patches advisories",
        "determine vulnerability exploitability and remediation",
    ),
    "bugbounty": (
        "bug bounty report payload proof of concept impact reproduction steps",
        "test web application vulnerability class ssrf xss idor bypass",
    ),
    "dev": (
        "understand source code repository dependency function implementation tests",
        "fix code bug refactor stack trace api documentation",
    ),
    "cyberdefense": (
        "detect threat with sigma yara splunk kql siem edr incident response",
        "map behavior to mitre attack and build hunting queries",
    ),
}


@dataclass
class RoutePlan:
    query: str
    intent: str
    entities: dict[str, list[str]]
    selected_domains: list[str]
    scores: dict[str, float]
    plan_type: str
    retrieval_mode: str = "hybrid"
    filters: dict[str, Any] = field(default_factory=dict)


class RagRouter:
    def __init__(self, embedder: Any | None = None) -> None:
        self.classifier = QueryClassifier()
        self.embedder = embedder
        self.prototype_vectors: dict[str, list[float]] = {}
        if embedder:
            for domain, samples in SEMANTIC_PROTOTYPES.items():
                self.prototype_vectors[domain] = embedder.embed(" ".join(samples))

    def route(self, query: str, memory_context: dict[str, Any] | None = None, agent_role: str = "default") -> RoutePlan:
        classification = self.classifier.classify(query)
        semantic_scores = self._semantic_scores(classification.query)
        memory_scores = self._memory_scores(memory_context or {})
        agent_scores = self._agent_bias(agent_role)
        freshness_scores = self._freshness_scores(classification.query, classification.intent)

        scores: dict[str, float] = {}
        for domain in DOMAINS:
            scores[domain] = round(
                0.35 * classification.rule_scores.get(domain, 0.0)
                + 0.25 * semantic_scores.get(domain, 0.0)
                + 0.15 * classification.entity_scores.get(domain, 0.0)
                + 0.10 * memory_scores.get(domain, 0.0)
                + 0.10 * agent_scores.get(domain, 0.0)
                + 0.05 * freshness_scores.get(domain, 0.0),
                4,
            )
        self._apply_correlation_boosts(scores, classification.entities, classification.intent)

        selected = self._select_domains(scores)
        filters = self._build_filters(classification.entities)
        return RoutePlan(
            query=classification.query,
            intent=classification.intent,
            entities=classification.entities,
            selected_domains=selected,
            scores=scores,
            plan_type="parallel" if len(selected) > 1 else "single",
            filters=filters,
        )

    def _semantic_scores(self, query: str) -> dict[str, float]:
        if not self.embedder or not self.prototype_vectors:
            lowered = query.lower()
            return {
                domain: min(1.0, sum(term in lowered for sample in samples for term in sample.split()) / 8.0)
                for domain, samples in SEMANTIC_PROTOTYPES.items()
            }
        query_vector = self.embedder.embed(query)
        return {
            domain: max(0.0, self.embedder.cosine(query_vector, vector))
            for domain, vector in self.prototype_vectors.items()
        }

    def _select_domains(self, scores: dict[str, float]) -> list[str]:
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        selected = [domain for domain, score in ordered if score >= config.secondary_threshold]
        if selected:
            return selected[:3]
        fallback = [domain for domain, score in ordered if score >= config.fallback_threshold]
        return (fallback or [ordered[0][0]])[:2]

    def _build_filters(self, entities: dict[str, list[str]]) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if entities.get("cves"):
            filters["cves"] = entities["cves"]
        if entities.get("domains"):
            filters["domains"] = entities["domains"]
        if entities.get("ips"):
            filters["ips"] = entities["ips"]
        if entities.get("mitre_techniques"):
            filters["mitre_techniques"] = entities["mitre_techniques"]
        if entities.get("paths"):
            filters["paths"] = entities["paths"]
        return filters

    def _memory_scores(self, memory_context: dict[str, Any]) -> dict[str, float]:
        scores = {domain: 0.0 for domain in DOMAINS}
        for domain in memory_context.get("recent_domains", []):
            if domain in scores:
                scores[domain] = 0.6
        if memory_context.get("active_cve"):
            scores["cve"] = max(scores["cve"], 0.8)
        if memory_context.get("active_asset"):
            scores["osint"] = max(scores["osint"], 0.6)
        return scores

    def _apply_correlation_boosts(self, scores: dict[str, float], entities: dict[str, list[str]], intent: str) -> None:
        has_ioc = bool(entities.get("domains") or entities.get("ips") or entities.get("emails") or entities.get("hashes"))
        has_cve = bool(entities.get("cves"))
        if has_cve and has_ioc:
            scores["cve"] = min(1.0, scores["cve"] + 0.30)
            scores["osint"] = min(1.0, scores["osint"] + 0.35)
        if has_cve and intent in {"exploitability", "detection"}:
            scores["cve"] = min(1.0, scores["cve"] + 0.20)
        if intent == "exploitability":
            scores["osint"] = min(1.0, scores["osint"] + 0.20)
        if intent == "detection":
            scores["cyberdefense"] = min(1.0, scores["cyberdefense"] + 0.35)

    def _agent_bias(self, agent_role: str) -> dict[str, float]:
        role_map = {
            "osint": "osint",
            "security": "cyberdefense",
            "defense": "cyberdefense",
            "developer": "dev",
            "coder": "dev",
            "bugbounty": "bugbounty",
            "vuln": "cve",
        }
        scores = {domain: 0.0 for domain in DOMAINS}
        domain = role_map.get(agent_role.lower())
        if domain:
            scores[domain] = 0.5
        return scores

    def _freshness_scores(self, query: str, intent: str) -> dict[str, float]:
        scores = {domain: 0.0 for domain in DOMAINS}
        if any(term in query.lower() for term in ("latest", "recent", "today", "now", "in the wild")):
            scores["cve"] = 0.8
            scores["osint"] = 0.8
            scores["cyberdefense"] = 0.5
        if intent in {"exploitability", "detection"}:
            scores["cve"] = max(scores["cve"], 0.6)
            scores["cyberdefense"] = max(scores["cyberdefense"], 0.6)
        return scores
