from __future__ import annotations

from dataclasses import asdict, dataclass, field
from rag.shared.utils import stable_id, utc_now
from typing import Literal


RelationshipType = Literal[
    "uses",
    "targets",
    "associated_with",
    "operates",
    "hosts",
    "resolves_to",
    "attributed_to",
    "overlaps_with",
]


@dataclass(slots=True)
class AttackInfrastructure:
    value: str
    infra_type: Literal["ip", "domain", "url", "asn", "cluster"]
    cluster: str = ""
    first_seen: str = ""
    last_seen: str = ""
    confidence: float = 0.7
    tags: list[str] = field(default_factory=list)

    @property
    def infra_id(self) -> str:
        return f"infra:{self.infra_type}:{stable_id(self.value)}"

    def to_payload(self) -> dict[str, object]:
        return asdict(self) | {"infra_id": self.infra_id}


@dataclass(slots=True)
class MalwareFamily:
    name: str
    aliases: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    first_seen: str = ""
    description: str = ""

    @property
    def malware_id(self) -> str:
        return f"malware:{stable_id(self.name.lower())}"

    def to_payload(self) -> dict[str, object]:
        return asdict(self) | {"malware_id": self.malware_id}


@dataclass(slots=True)
class Campaign:
    name: str
    aliases: list[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    targets: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    techniques: list[str] = field(default_factory=list)
    infrastructure: list[AttackInfrastructure] = field(default_factory=list)
    description: str = ""

    @property
    def campaign_id(self) -> str:
        return f"campaign:{stable_id(self.name.lower(), self.start_date)}"

    def to_payload(self) -> dict[str, object]:
        return asdict(self) | {
            "campaign_id": self.campaign_id,
            "infrastructure": [item.to_payload() for item in self.infrastructure],
        }


@dataclass(slots=True)
class ActorRelationship:
    subject: str
    predicate: RelationshipType
    object: str
    confidence: float = 0.7
    source: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def relationship_id(self) -> str:
        return f"relationship:{stable_id(self.subject, self.predicate, self.object)}"

    def to_payload(self) -> dict[str, object]:
        return asdict(self) | {"relationship_id": self.relationship_id}


@dataclass(slots=True)
class ThreatActor:
    name: str
    aliases: list[str] = field(default_factory=list)
    actor_type: str = "apt"
    country: str = ""
    motivation: list[str] = field(default_factory=list)
    sophistication: str = ""
    targets: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    malware: list[MalwareFamily] = field(default_factory=list)
    campaigns: list[Campaign] = field(default_factory=list)
    infrastructure: list[AttackInfrastructure] = field(default_factory=list)
    relationships: list[ActorRelationship] = field(default_factory=list)
    techniques: list[str] = field(default_factory=list)
    description: str = ""
    source_uri: str = "threat-actor:manual"
    trust_level: str = "semi_trusted"
    ingested_at: str = field(default_factory=utc_now)
    domain: str = "threat_actor"

    @property
    def actor_id(self) -> str:
        return f"actor:{stable_id(self.name.lower())}"

    @property
    def doc_id(self) -> str:
        return self.actor_id

    @property
    def body(self) -> str:
        return "\n".join(
            part for part in [
                f"Actor: {self.name}",
                f"Aliases: {', '.join(self.aliases)}",
                f"Country: {self.country}",
                f"Motivation: {', '.join(self.motivation)}",
                f"Targets: {', '.join(self.targets)}",
                f"Sectors: {', '.join(self.sectors)}",
                f"Tools: {', '.join(self.tools)}",
                f"Malware: {', '.join(item.name for item in self.malware)}",
                f"Campaigns: {', '.join(item.name for item in self.campaigns)}",
                f"Infrastructure: {', '.join(item.value for item in self.infrastructure)}",
                f"MITRE Techniques: {', '.join(self.techniques)}",
                self.description,
            ]
            if part
        )

    def to_payload(self) -> dict[str, object]:
        malware_names = sorted({item.name for item in self.malware})
        campaign_names = sorted({item.name for item in self.campaigns})
        domains = sorted({item.value for item in self.infrastructure if item.infra_type == "domain"})
        ips = sorted({item.value for item in self.infrastructure if item.infra_type == "ip"})
        clusters = sorted({item.cluster or item.value for item in self.infrastructure if item.infra_type == "cluster" or item.cluster})
        return {
            "doc_id": self.doc_id,
            "domain": self.domain,
            "source_type": "threat_actor",
            "source_uri": self.source_uri,
            "title": self.name,
            "actor_id": self.actor_id,
            "actor_names": [self.name] + self.aliases,
            "actor_type": self.actor_type,
            "country": self.country,
            "motivation": self.motivation,
            "sophistication": self.sophistication,
            "targets": self.targets,
            "sectors": self.sectors,
            "tools": self.tools,
            "malware_families": malware_names,
            "campaigns": campaign_names,
            "infrastructure": [item.to_payload() for item in self.infrastructure],
            "domains": domains,
            "ips": ips,
            "clusters": clusters,
            "relationships": [item.to_payload() for item in self.relationships],
            "relationship_tags": sorted({tag for rel in self.relationships for tag in rel.tags} | {rel.predicate for rel in self.relationships}),
            "mitre_techniques": self.techniques,
            "description": self.description,
            "trust_level": self.trust_level,
            "ingested_at": self.ingested_at,
        }


@dataclass(slots=True)
class ThreatActorChunk:
    chunk_id: str
    doc_id: str
    text: str
    title: str
    source_uri: str
    chunk_index: int
    section: str
    metadata: dict[str, object]
    domain: str = "threat_actor"


RagChunk = ThreatActorChunk
