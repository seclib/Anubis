from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


NODE_LABELS = {
    "ip": ("IP", "value"),
    "domain": ("Domain", "value"),
    "email": ("Email", "value"),
    "cve": ("CVE", "id"),
    "organization": ("Organization", "name"),
    "org": ("Organization", "name"),
    "threat_actor": ("ThreatActor", "name"),
    "actor": ("ThreatActor", "name"),
}

RELATIONSHIPS = {
    "owns": "OWNS",
    "linked_to": "LINKS_TO",
    "links_to": "LINKS_TO",
    "exploits": "EXPLOITS",
    "exploited_by": "EXPLOITS",
    "affects": "AFFECTS",
    "affected_by": "AFFECTS",
    "associated_with": "ASSOCIATED_WITH",
}


@dataclass(frozen=True)
class GraphNode:
    kind: str
    value: str
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return NODE_LABELS.get(self.kind, (self.kind.title().replace("_", ""), "value"))[0]

    @property
    def key(self) -> str:
        return NODE_LABELS.get(self.kind, ("Entity", "value"))[1]


@dataclass(frozen=True)
class GraphRelationship:
    source: GraphNode
    relationship: str
    target: GraphNode
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        return RELATIONSHIPS.get(self.relationship, self.relationship.upper())


class RelationshipMapper:
    def map_record(self, record: dict[str, Any]) -> tuple[list[GraphNode], list[GraphRelationship]]:
        nodes: dict[tuple[str, str], GraphNode] = {}
        relationships: list[GraphRelationship] = []

        def add(kind: str, value: Any, **properties: Any) -> GraphNode | None:
            if value is None or value == "":
                return None
            node = GraphNode(kind=kind, value=str(value), properties={k: v for k, v in properties.items() if v is not None})
            nodes[(node.kind, node.value)] = node
            return node

        domain = add("domain", record.get("domain") or record.get("hostname"), source=record.get("source"))
        ip = add("ip", record.get("ip") or record.get("address"), source=record.get("source"))
        email = add("email", record.get("email"), source=record.get("source"))
        cve = add("cve", record.get("cve") or record.get("cve_id"), cvss=record.get("cvss"))
        org = add("organization", record.get("organization") or record.get("org"))
        actor = add("threat_actor", record.get("actor") or record.get("threat_actor"))

        if org and domain:
            relationships.append(GraphRelationship(org, "owns", domain))
        if domain and ip:
            relationships.append(GraphRelationship(domain, "links_to", ip))
        if email and domain:
            relationships.append(GraphRelationship(email, "associated_with", domain))
        if actor and cve:
            relationships.append(GraphRelationship(actor, "exploits", cve))
        if cve and org:
            relationships.append(GraphRelationship(cve, "affects", org))
        if actor and domain:
            relationships.append(GraphRelationship(actor, "associated_with", domain))
        if actor and ip:
            relationships.append(GraphRelationship(actor, "associated_with", ip))

        for raw in record.get("relationships", []) or []:
            if not isinstance(raw, dict):
                continue
            source = add(raw.get("source_type", "entity"), raw.get("source"))
            target = add(raw.get("target_type", "entity"), raw.get("target"))
            rel_type = raw.get("type") or raw.get("relationship") or "associated_with"
            if source and target:
                relationships.append(GraphRelationship(source, rel_type, target, raw.get("properties") or {}))

        return list(nodes.values()), relationships
