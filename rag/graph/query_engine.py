from __future__ import annotations

from typing import Any

from rag.graph.neo4j_client import Neo4jClient
from rag.graph.relationship_mapper import NODE_LABELS


class GraphQueryEngine:
    def __init__(self, client: Neo4jClient | None = None) -> None:
        self.client = client or Neo4jClient()

    def neighborhood(self, kind: str, value: str, depth: int = 2, limit: int = 50) -> list[dict[str, Any]]:
        label, key = NODE_LABELS.get(kind, (kind.title().replace("_", ""), "value"))
        cypher = (
            f"MATCH path=(n:{label} {{{key}: $value}})-[*1..{max(1, min(depth, 5))}]-(m) "
            "RETURN path LIMIT $limit"
        )
        return self.client.run(cypher, {"value": value, "limit": limit})

    def attack_surface(self, organization: str, limit: int = 100) -> list[dict[str, Any]]:
        cypher = (
            "MATCH (o:Organization {name: $organization})-[:OWNS|LINKS_TO*1..3]-(asset) "
            "OPTIONAL MATCH (asset)<-[:AFFECTS]-(c:CVE) "
            "RETURN asset, collect(DISTINCT c.id) AS cves LIMIT $limit"
        )
        return self.client.run(cypher, {"organization": organization, "limit": limit})

    def actor_profile(self, actor: str, limit: int = 100) -> list[dict[str, Any]]:
        cypher = (
            "MATCH (a:ThreatActor {name: $actor})-[r]-(entity) "
            "RETURN type(r) AS relationship, entity LIMIT $limit"
        )
        return self.client.run(cypher, {"actor": actor, "limit": limit})

    def exploit_chain(self, start_cve: str, depth: int = 3, limit: int = 25) -> list[dict[str, Any]]:
        cypher = (
            f"MATCH path=(c:CVE {{id: $cve}})-[:AFFECTS|EXPLOITS|ASSOCIATED_WITH*1..{max(1, min(depth, 5))}]-(n) "
            "RETURN path LIMIT $limit"
        )
        return self.client.run(cypher, {"cve": start_cve, "limit": limit})
