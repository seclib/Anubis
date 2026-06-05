from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from rag.graph.neo4j_client import Neo4jClient
from rag.graph.relationship_mapper import GraphNode, GraphRelationship, RelationshipMapper


logger = logging.getLogger("anubis.rag.graph.builder")


class GraphBuilder:
    def __init__(self, client: Neo4jClient | None = None, mapper: RelationshipMapper | None = None) -> None:
        self.client = client or Neo4jClient()
        self.mapper = mapper or RelationshipMapper()

    def ingest_records(self, records: Iterable[dict[str, Any]]) -> dict[str, int]:
        self.client.ensure_constraints()
        node_count = 0
        relationship_count = 0
        for record in records:
            nodes, relationships = self.mapper.map_record(record)
            for node in nodes:
                self.upsert_node(node)
                node_count += 1
            for relationship in relationships:
                self.upsert_relationship(relationship)
                relationship_count += 1
        logger.info("graph ingest complete nodes=%s relationships=%s", node_count, relationship_count)
        return {"nodes": node_count, "relationships": relationship_count}

    def upsert_node(self, node: GraphNode) -> None:
        self.client.merge_node(node.label, node.key, node.value, node.properties)

    def upsert_relationship(self, relationship: GraphRelationship) -> None:
        self.client.merge_relationship(
            relationship.source.label,
            relationship.source.key,
            relationship.source.value,
            relationship.type,
            relationship.target.label,
            relationship.target.key,
            relationship.target.value,
            relationship.properties,
        )
