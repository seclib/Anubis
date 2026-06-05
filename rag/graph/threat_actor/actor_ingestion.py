from __future__ import annotations

import argparse
import logging
from pathlib import Path

from rag.shared.dedupe import SeenSet
from rag.shared.embedding import EmbeddingPipeline as OsintEmbeddingPipeline
from rag.shared.io import load_json_records
from rag.graph.threat_actor.campaign_indexer import CampaignIndexer
from rag.graph.threat_actor.malware_mapper import MalwareMapper
from rag.graph.threat_actor.schema import ActorRelationship, AttackInfrastructure, ThreatActor, ThreatActorChunk, stable_id
from rag.shared.qdrant_client import QdrantVectorStore


logger = logging.getLogger("anubis.rag.graph.threat_actor.ingestion")


class ThreatActorIngestion:
    domain = "threat_actor"

    def __init__(
        self,
        malware_mapper: MalwareMapper | None = None,
        campaign_indexer: CampaignIndexer | None = None,
        embedder: OsintEmbeddingPipeline | None = None,
        store: QdrantVectorStore | None = None,
    ) -> None:
        self.malware_mapper = malware_mapper or MalwareMapper()
        self.campaign_indexer = campaign_indexer or CampaignIndexer()
        self.embedder = embedder or OsintEmbeddingPipeline()
        self.store = store or QdrantVectorStore(self.embedder)
        self._seen = SeenSet()

    def load_file(self, path: str | Path) -> list[ThreatActor]:
        records = self._load_records(path)
        return [self.actor_from_record(record) for record in records]

    def actor_from_record(self, record: dict[str, object]) -> ThreatActor:
        actor = ThreatActor(
            name=str(record.get("name") or record.get("actor") or record.get("group") or "unknown-actor"),
            aliases=[str(item) for item in record.get("aliases", [])],
            actor_type=str(record.get("actor_type") or record.get("type") or "apt"),
            country=str(record.get("country") or record.get("origin") or ""),
            motivation=[str(item) for item in record.get("motivation", [])],
            sophistication=str(record.get("sophistication") or ""),
            targets=[str(item) for item in record.get("targets", [])],
            sectors=[str(item) for item in record.get("sectors", [])],
            tools=[str(item) for item in record.get("tools", [])],
            techniques=[str(item).upper() for item in record.get("techniques", [])],
            description=str(record.get("description") or record.get("summary") or record.get("body") or ""),
            source_uri=str(record.get("source_uri") or record.get("url") or "threat-actor:manual"),
            trust_level=str(record.get("trust_level") or "semi_trusted"),
        )
        for malware_record in record.get("malware", []):
            if isinstance(malware_record, dict):
                self.malware_mapper.map_to_actor(actor, self.malware_mapper.malware_from_record(malware_record), source=actor.source_uri)
            else:
                self.malware_mapper.map_to_actor(actor, self.malware_mapper.malware_from_record({"name": malware_record}), source=actor.source_uri)
        for campaign_record in record.get("campaigns", []):
            if isinstance(campaign_record, dict):
                self.campaign_indexer.link_campaign_to_actor(actor, self.campaign_indexer.campaign_from_record(campaign_record))
        for infra_record in record.get("infrastructure", []):
            if isinstance(infra_record, dict):
                actor.infrastructure.append(self.campaign_indexer.infrastructure_from_record(infra_record))
        actor.infrastructure = self.campaign_indexer._dedupe_infra(actor.infrastructure)
        actor.relationships.extend(self._relationships_from_record(actor, record))
        return actor

    def ingest_file(self, path: str | Path, batch_size: int = 64) -> int:
        return self.index_actors(self.load_file(path), batch_size=batch_size)

    def index_actors(self, actors: list[ThreatActor], batch_size: int = 64) -> int:
        chunks = [chunk for actor in self._dedupe(actors) for chunk in self.chunk_actor(actor)]
        indexed = self.store.upsert_chunks(self.domain, chunks, batch_size=batch_size)
        logger.info("indexed threat actors=%s chunks=%s", len(actors), indexed)
        return indexed

    def chunk_actor(self, actor: ThreatActor) -> list[ThreatActorChunk]:
        payload = actor.to_payload()
        sections = {
            "profile": actor.body,
            "malware": "\n".join(f"{item.name}: {item.description} {' '.join(item.capabilities)}" for item in actor.malware),
            "campaigns": "\n".join(f"{item.name}: {item.description} {' '.join(item.techniques)}" for item in actor.campaigns),
            "infrastructure": "\n".join(f"{item.infra_type}:{item.value} cluster={item.cluster} tags={' '.join(item.tags)}" for item in actor.infrastructure),
            "relationships": "\n".join(f"{rel.subject} {rel.predicate} {rel.object} confidence={rel.confidence} tags={' '.join(rel.tags)}" for rel in actor.relationships),
        }
        chunks: list[ThreatActorChunk] = []
        for section, text in sections.items():
            if text.strip():
                chunks.append(
                    ThreatActorChunk(
                        chunk_id=f"{actor.doc_id}:{section}:{stable_id(text)[:12]}",
                        doc_id=actor.doc_id,
                        text=text,
                        title=actor.name,
                        source_uri=actor.source_uri,
                        chunk_index=len(chunks),
                        section=section,
                        metadata=payload | {"section": section},
                    )
                )
        return chunks

    def search(
        self,
        query: str,
        top_k: int = 10,
        actor: str | None = None,
        malware: str | None = None,
        campaign: str | None = None,
        cluster: str | None = None,
    ) -> list[dict[str, object]]:
        filters: dict[str, object] = {}
        if actor:
            filters["actor_names"] = [actor]
        if malware:
            filters["malware_families"] = [malware]
        if campaign:
            filters["campaigns"] = [campaign]
        if cluster:
            filters["clusters"] = [cluster]
        return self.store.search(self.domain, query, top_k=top_k, filters=filters)

    def _load_records(self, path: str | Path) -> list[dict[str, object]]:
        return load_json_records(path, ("actors", "groups", "items", "data", "results"))

    def _relationships_from_record(self, actor: ThreatActor, record: dict[str, object]) -> list[ActorRelationship]:
        relationships: list[ActorRelationship] = []
        for target in actor.targets:
            relationships.append(ActorRelationship(actor.name, "targets", target, source=actor.source_uri, tags=["target"]))
        for tool in actor.tools:
            relationships.append(ActorRelationship(actor.name, "uses", tool, source=actor.source_uri, tags=["tool"]))
        for raw in record.get("relationships", []):
            if not isinstance(raw, dict):
                continue
            relationships.append(
                ActorRelationship(
                    subject=str(raw.get("subject") or actor.name),
                    predicate=str(raw.get("predicate") or "associated_with"),
                    object=str(raw.get("object") or ""),
                    confidence=float(raw.get("confidence") or 0.7),
                    source=str(raw.get("source") or actor.source_uri),
                    tags=[str(item) for item in raw.get("tags", [])],
                )
            )
        return relationships

    def _dedupe(self, actors: list[ThreatActor]) -> list[ThreatActor]:
        return self._seen.unique(actors, lambda actor: actor.doc_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="ANUBIS Threat Actor RAG")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest")
    ingest.add_argument("path")
    ingest.add_argument("--batch-size", type=int, default=64)

    query = sub.add_parser("query")
    query.add_argument("text", nargs="+")
    query.add_argument("--top-k", type=int, default=10)
    query.add_argument("--actor")
    query.add_argument("--malware")
    query.add_argument("--campaign")
    query.add_argument("--cluster")

    args = parser.parse_args()
    pipeline = ThreatActorIngestion()
    if args.command == "ingest":
        print(f"Indexed {pipeline.ingest_file(args.path, batch_size=args.batch_size)} threat actor chunks.")
    elif args.command == "query":
        for result in pipeline.search(" ".join(args.text), top_k=args.top_k, actor=args.actor, malware=args.malware, campaign=args.campaign, cluster=args.cluster):
            print(f"{result.get('score', 0):.3f} {result.get('title')} {result.get('section')} {result.get('source_uri')}")


if __name__ == "__main__":
    main()
