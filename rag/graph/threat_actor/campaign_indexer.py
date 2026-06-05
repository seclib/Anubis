from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from rag.graph.threat_actor.schema import ActorRelationship, AttackInfrastructure, Campaign, ThreatActor


IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DOMAIN_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,63}\b", re.I)
URL_RE = re.compile(r"https?://[^\s<>'\")]+", re.I)
MITRE_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.I)


class CampaignIndexer:
    def campaign_from_record(self, record: dict[str, object]) -> Campaign:
        body = " ".join(str(record.get(key) or "") for key in ("description", "body", "summary", "notes"))
        explicit_infra = record.get("infrastructure") or []
        infrastructure = [self.infrastructure_from_record(item) for item in explicit_infra if isinstance(item, dict)]
        infrastructure.extend(self.extract_infrastructure(body))
        return Campaign(
            name=str(record.get("name") or record.get("campaign") or "unknown-campaign"),
            aliases=[str(item) for item in record.get("aliases", [])],
            start_date=str(record.get("start_date") or record.get("first_seen") or ""),
            end_date=str(record.get("end_date") or record.get("last_seen") or ""),
            targets=[str(item) for item in record.get("targets", [])],
            regions=[str(item) for item in record.get("regions", [])],
            sectors=[str(item) for item in record.get("sectors", [])],
            techniques=sorted(set(str(item).upper() for item in record.get("techniques", [])) | set(MITRE_RE.findall(body))),
            infrastructure=self._dedupe_infra(infrastructure),
            description=body,
        )

    def infrastructure_from_record(self, record: dict[str, object]) -> AttackInfrastructure:
        value = str(record.get("value") or record.get("domain") or record.get("ip") or record.get("url") or record.get("cluster") or "")
        infra_type = str(record.get("type") or self.infer_infra_type(value))
        normalized = self.normalize_infra(value, infra_type)
        return AttackInfrastructure(
            value=normalized,
            infra_type=infra_type,
            cluster=str(record.get("cluster") or ""),
            first_seen=str(record.get("first_seen") or ""),
            last_seen=str(record.get("last_seen") or ""),
            confidence=float(record.get("confidence") or 0.7),
            tags=[str(item) for item in record.get("tags", [])],
        )

    def extract_infrastructure(self, text: str) -> list[AttackInfrastructure]:
        infrastructure: list[AttackInfrastructure] = []
        for value in URL_RE.findall(text):
            normalized = self.normalize_infra(value, "url")
            infrastructure.append(AttackInfrastructure(value=normalized, infra_type="url"))
            host = urlparse(normalized).hostname
            if host:
                infrastructure.append(AttackInfrastructure(value=self.normalize_infra(host, "domain"), infra_type="domain"))
        for value in DOMAIN_RE.findall(text):
            infrastructure.append(AttackInfrastructure(value=self.normalize_infra(value, "domain"), infra_type="domain"))
        for value in IP_RE.findall(text):
            normalized = self.normalize_infra(value, "ip")
            if normalized:
                infrastructure.append(AttackInfrastructure(value=normalized, infra_type="ip"))
        return self._dedupe_infra(infrastructure)

    def link_campaign_to_actor(self, actor: ThreatActor, campaign: Campaign, confidence: float = 0.75) -> list[ActorRelationship]:
        relationships = [
            ActorRelationship(
                subject=actor.name,
                predicate="operates",
                object=campaign.name,
                confidence=confidence,
                source=actor.source_uri,
                tags=["campaign"],
            )
        ]
        for infra in campaign.infrastructure:
            relationships.append(
                ActorRelationship(
                    subject=campaign.name,
                    predicate="uses",
                    object=infra.value,
                    confidence=infra.confidence,
                    source=actor.source_uri,
                    tags=["infrastructure", infra.infra_type, infra.cluster],
                )
            )
        actor.relationships.extend(relationships)
        if campaign.name not in {item.name for item in actor.campaigns}:
            actor.campaigns.append(campaign)
        existing = {item.value for item in actor.infrastructure}
        actor.infrastructure.extend(item for item in campaign.infrastructure if item.value not in existing)
        return relationships

    def infer_infra_type(self, value: str) -> str:
        if value.startswith(("http://", "https://")):
            return "url"
        try:
            ipaddress.ip_address(value)
            return "ip"
        except ValueError:
            pass
        if "." in value:
            return "domain"
        return "cluster"

    def normalize_infra(self, value: str, infra_type: str) -> str:
        value = value.strip()
        if infra_type == "ip":
            try:
                return str(ipaddress.ip_address(value))
            except ValueError:
                return ""
        if infra_type == "domain":
            return value.strip(".").lower()
        if infra_type == "url":
            parsed = urlparse(value)
            host = (parsed.hostname or "").lower()
            return f"{parsed.scheme.lower() or 'https'}://{host}{parsed.path or ''}"
        return value.lower()

    def _dedupe_infra(self, infrastructure: list[AttackInfrastructure]) -> list[AttackInfrastructure]:
        seen: set[str] = set()
        unique: list[AttackInfrastructure] = []
        for item in infrastructure:
            key = f"{item.infra_type}:{item.value}"
            if not item.value or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique
