from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

try:
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover - optional runtime dependency
    GraphDatabase = None


logger = logging.getLogger("anubis.rag.graph.neo4j")


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "anubis"
    database: str = "neo4j"


class Neo4jClient(AbstractContextManager["Neo4jClient"]):
    def __init__(self, config: Neo4jConfig | None = None) -> None:
        self.config = config or Neo4jConfig()
        self.driver = (
            GraphDatabase.driver(self.config.uri, auth=(self.config.username, self.config.password))
            if GraphDatabase
            else None
        )

    @property
    def available(self) -> bool:
        return self.driver is not None

    def close(self) -> None:
        if self.driver:
            self.driver.close()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def run(self, cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if not self.driver:
            logger.warning("neo4j driver unavailable; skipped query")
            return []
        with self.driver.session(database=self.config.database) as session:
            result = session.run(cypher, parameters or {})
            return [dict(record) for record in result]

    def ensure_constraints(self) -> None:
        constraints = [
            "CREATE CONSTRAINT anubis_ip IF NOT EXISTS FOR (n:IP) REQUIRE n.value IS UNIQUE",
            "CREATE CONSTRAINT anubis_domain IF NOT EXISTS FOR (n:Domain) REQUIRE n.value IS UNIQUE",
            "CREATE CONSTRAINT anubis_email IF NOT EXISTS FOR (n:Email) REQUIRE n.value IS UNIQUE",
            "CREATE CONSTRAINT anubis_cve IF NOT EXISTS FOR (n:CVE) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT anubis_org IF NOT EXISTS FOR (n:Organization) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT anubis_actor IF NOT EXISTS FOR (n:ThreatActor) REQUIRE n.name IS UNIQUE",
        ]
        for constraint in constraints:
            self.run(constraint)

    def merge_node(self, label: str, key: str, value: str, properties: dict[str, Any] | None = None) -> None:
        cypher = f"MERGE (n:{label} {{{key}: $value}}) SET n += $properties"
        self.run(cypher, {"value": value, "properties": properties or {}})

    def merge_relationship(
        self,
        left_label: str,
        left_key: str,
        left_value: str,
        relationship: str,
        right_label: str,
        right_key: str,
        right_value: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        cypher = (
            f"MERGE (a:{left_label} {{{left_key}: $left_value}}) "
            f"MERGE (b:{right_label} {{{right_key}: $right_value}}) "
            f"MERGE (a)-[r:{relationship}]->(b) "
            "SET r += $properties"
        )
        self.run(
            cypher,
            {
                "left_value": left_value,
                "right_value": right_value,
                "properties": properties or {},
            },
        )
