#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging

from pipelines.update_pipeline import UpdatePipeline
from rag.shared.embedding import EmbeddingService
from rag.shared.config import config
from rag.shared.query_router import RagRouter, RoutePlan
from rag.shared.qdrant_client import QdrantVectorStore


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("anubis.rag")


class AnubisRagSystem:
    def __init__(self) -> None:
        self.embedder = EmbeddingService()
        self.store = QdrantVectorStore(self.embedder)
        self.router = RagRouter(self.embedder)

    def query(self, query: str, top_k: int | None = None, agent_role: str = "default") -> dict[str, object]:
        route = self.router.route(query, agent_role=agent_role)
        results = self.retrieve(route, top_k or config.default_top_k)
        return {
            "query": query,
            "route": {
                "intent": route.intent,
                "selected_domains": route.selected_domains,
                "scores": route.scores,
                "plan_type": route.plan_type,
                "filters": route.filters,
            },
            "answer": self.render_response(query, route, results),
            "results": results,
        }

    def retrieve(self, route: RoutePlan, top_k: int) -> list[dict[str, object]]:
        all_results: list[dict[str, object]] = []
        per_domain_k = max(2, top_k)
        for domain in route.selected_domains:
            all_results.extend(self.store.search(domain, route.query, per_domain_k, filters=self.filters_for_domain(domain, route.filters)))
        return self.fuse_results(all_results)[:top_k]

    def filters_for_domain(self, domain: str, filters: dict[str, object]) -> dict[str, object]:
        allowed = {
            "osint": {"domains", "ips", "emails", "hashes", "cves"},
            "cve": {"cves"},
            "bugbounty": {"vulnerability_types", "framework"},
            "dev": {"language", "path", "paths"},
            "cyberdefense": {"mitre_techniques", "mitre_tactics", "rule_type", "log_source"},
            "defense": {"mitre_techniques", "mitre_tactics", "rule_type", "log_source"},
            "threat_actor": {"actor_names", "malware_families", "campaigns", "clusters"},
            "tools": {"tools", "phase", "tool_tags"},
            "memory": {"session_ids", "memory_types", "investigation_ids", "memory_tags"},
        }.get(domain, set(filters))
        return {key: value for key, value in filters.items() if key in allowed}

    def fuse_results(self, results: list[dict[str, object]]) -> list[dict[str, object]]:
        deduped: dict[str, dict[str, object]] = {}
        for result in results:
            key = str(result.get("chunk_id") or result.get("doc_id") or result.get("source_uri"))
            current = deduped.get(key)
            if current is None or float(result.get("score", 0.0)) > float(current.get("score", 0.0)):
                deduped[key] = result
        return sorted(deduped.values(), key=lambda item: float(item.get("score", 0.0)), reverse=True)

    def render_response(self, query: str, route: RoutePlan, results: list[dict[str, object]]) -> str:
        if not results:
            return (
                f"No indexed evidence was found for '{query}'. "
                f"Selected RAG domains were {', '.join(route.selected_domains)}. "
                "Run ingestion first, for example: python main.py ingest-demo"
            )
        lines = [
            f"ANUBIS routed this query to: {', '.join(route.selected_domains)}.",
            f"Intent: {route.intent}. Top evidence:",
        ]
        for index, result in enumerate(results[:5], start=1):
            title = result.get("title") or result.get("doc_id") or "untitled"
            domain = result.get("domain", "unknown")
            score = float(result.get("score", 0.0))
            text = " ".join(str(result.get("text", "")).split())[:360]
            source = result.get("source_uri", "unknown-source")
            lines.append(f"{index}. [{domain}] {title} score={score:.3f} source={source}\n   {text}")
        return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ANUBIS multi-RAG system")
    sub = parser.add_subparsers(dest="command")

    query_parser = sub.add_parser("query", help="route and retrieve a query")
    query_parser.add_argument("text", nargs="+")
    query_parser.add_argument("--top-k", type=int, default=config.default_top_k)
    query_parser.add_argument("--agent-role", default="default")
    query_parser.add_argument("--json", action="store_true")

    sub.add_parser("ingest-demo", help="ingest built-in demo intelligence")

    ingest = sub.add_parser("ingest", help="ingest data into one or more RAG domains")
    ingest.add_argument("--osint-jsonl")
    ingest.add_argument("--nvd-json")
    ingest.add_argument("--kev-json")
    ingest.add_argument("--bugbounty-jsonl")
    ingest.add_argument("--code-path")
    ingest.add_argument("--stackoverflow-jsonl")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest-demo":
        total = UpdatePipeline().ingest_demo()
        print(f"Ingested {total} chunks into ANUBIS RAG.")
        return

    if args.command == "ingest":
        pipeline = UpdatePipeline()
        total = 0
        if args.osint_jsonl:
            total += pipeline.ingest_osint_jsonl(args.osint_jsonl)
        if args.nvd_json:
            total += pipeline.ingest_nvd_json(args.nvd_json)
        if args.kev_json:
            total += pipeline.ingest_kev_json(args.kev_json)
        if args.bugbounty_jsonl:
            total += pipeline.ingest_bugbounty_jsonl(args.bugbounty_jsonl)
        if args.code_path:
            total += pipeline.ingest_code_path(args.code_path)
        if args.stackoverflow_jsonl:
            total += pipeline.ingest_stackoverflow_jsonl(args.stackoverflow_jsonl)
        print(f"Ingested {total} chunks into ANUBIS RAG.")
        return

    if args.command == "query":
        system = AnubisRagSystem()
        response = system.query(" ".join(args.text), top_k=args.top_k, agent_role=args.agent_role)
        if args.json:
            print(json.dumps(response, indent=2, default=str))
        else:
            print(response["answer"])
        return

    parser.print_help()


if __name__ == "__main__":
    main()
