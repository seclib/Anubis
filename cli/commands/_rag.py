from __future__ import annotations

import json
from typing import Any

from cli.core.context import CliContext
from cli.core.dispatcher import CommandResult
from cli.utils.parser import ParsedCommand


def query_rag(domain: str, command: ParsedCommand, ctx: CliContext) -> CommandResult:
    query = command.raw_args.strip()
    if not query:
        return CommandResult(f"{domain.upper()} RAG", "error", f"usage: /{domain} <query>")
    try:
        from rag.shared.embedding import EmbeddingService
        from rag.shared.qdrant_client import QdrantVectorStore

        store = QdrantVectorStore(EmbeddingService())
        results = store.search(domain, query, top_k=ctx.config.default_top_k)
    except Exception as exc:
        return CommandResult(f"{domain.upper()} RAG {query}", "failed", f"retrieval failed: {exc}")
    return CommandResult(f"{domain.upper()} RAG {query}", {"rag": domain, "results": str(len(results))}, _json(results))


def route_query(command: ParsedCommand, ctx: CliContext) -> CommandResult:
    query = command.raw_args.strip()
    if not query:
        return CommandResult("RAG Router", "error", "usage: /rag <query>")
    try:
        from rag.router import RagRouter

        router = RagRouter()
        plan = router.route(query)
        domains = list(plan.selected_domains)
        confidence = max((plan.scores.get(domain, 0.0) for domain in domains), default=0.0)
    except Exception as exc:
        return CommandResult("RAG Router", "failed", f"routing failed: {exc}")
    return CommandResult(
        f"RAG Router {query}",
        {"domains": ",".join(domains), "confidence": f"{confidence:.2f}"},
        _json(
            {
                "query": plan.query,
                "intent": plan.intent,
                "domains": domains,
                "confidence": confidence,
                "plan_type": plan.plan_type,
                "retrieval_mode": plan.retrieval_mode,
                "filters": plan.filters,
                "scores": plan.scores,
            }
        ),
    )


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)
