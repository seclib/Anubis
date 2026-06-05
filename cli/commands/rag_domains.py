"""Domain-specific RAG command handlers.

Migrated from anubis-cli/commands/ (bugbounty, cve, defense, dev, graph, osint, tools).
All domain commands route through ``query_rag`` which delegates to
``rag.shared.embedding.EmbeddingService`` + ``rag.shared.qdrant_client.QdrantVectorStore``.
"""
from __future__ import annotations

import json
from typing import Any

from config import QDRANT_URL


# ---------------------------------------------------------------------------
# Domain RAG query
# ---------------------------------------------------------------------------

_DEFAULT_TOP_K = 5


def query_rag(domain: str, query: str, *, top_k: int = _DEFAULT_TOP_K) -> dict[str, Any]:
    """Execute a domain-scoped RAG search and return a structured result dict."""
    if not query.strip():
        return {"task": f"{domain.upper()} RAG", "status": "error", "result": f"usage: /{domain} <query>"}
    try:
        from rag.shared.embedding import EmbeddingService
        from rag.shared.qdrant_client import QdrantVectorStore

        store = QdrantVectorStore(EmbeddingService())
        results = store.search(domain, query, top_k=top_k)
    except Exception as exc:
        return {"task": f"{domain.upper()} RAG {query}", "status": "failed", "result": f"retrieval failed: {exc}"}
    return {
        "task": f"{domain.upper()} RAG {query}",
        "status": {"rag": domain, "results": str(len(results))},
        "result": _json(results),
    }


def route_rag_query(query: str) -> dict[str, Any]:
    """Route a free-form RAG query through the multi-domain router."""
    if not query.strip():
        return {"task": "RAG Router", "status": "error", "result": "usage: /rag <query>"}
    try:
        from rag.shared.query_router import RagRouter

        router = RagRouter()
        plan = router.route(query)
        domains = list(plan.selected_domains)
        confidence = max((plan.scores.get(d, 0.0) for d in domains), default=0.0)
    except Exception as exc:
        return {"task": "RAG Router", "status": "failed", "result": f"routing failed: {exc}"}
    return {
        "task": f"RAG Router {query}",
        "status": {"domains": ",".join(domains), "confidence": f"{confidence:.2f}"},
        "result": _json({
            "query": plan.query,
            "intent": plan.intent,
            "domains": domains,
            "confidence": confidence,
            "plan_type": plan.plan_type,
            "retrieval_mode": plan.retrieval_mode,
            "filters": plan.filters,
            "scores": plan.scores,
        }),
    }


# ---------------------------------------------------------------------------
# Per-domain convenience handlers
# ---------------------------------------------------------------------------

def handle_osint(query: str) -> dict[str, Any]:
    return query_rag("osint", query)


def handle_cve(query: str) -> dict[str, Any]:
    return query_rag("cve", query)


def handle_bugbounty(query: str) -> dict[str, Any]:
    return query_rag("bugbounty", query)


def handle_dev(query: str) -> dict[str, Any]:
    return query_rag("dev", query)


def handle_defense(query: str) -> dict[str, Any]:
    return query_rag("defense", query)


def handle_graph(query: str) -> dict[str, Any]:
    return query_rag("graph", query)


def handle_tools(query: str) -> dict[str, Any]:
    return query_rag("tools", query)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


# Map of slash-command names to handlers for registration
DOMAIN_HANDLERS: dict[str, Any] = {
    "/rag": route_rag_query,
    "/osint": handle_osint,
    "/cve": handle_cve,
    "/bugbounty": handle_bugbounty,
    "/bug": handle_bugbounty,
    "/dev": handle_dev,
    "/code": handle_dev,
    "/defense": handle_defense,
    "/graph": handle_graph,
    "/tools": handle_tools,
    "/tooling": handle_tools,
}
