from __future__ import annotations

import json
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


DEFAULT_DOMAINS = ("osint", "cve", "bugbounty", "graph")
DOMAIN_ALIASES = {
    "bug": "bugbounty",
    "bug_bounty": "bugbounty",
    "defense": "cyberdefense",
    "blue": "cyberdefense",
}


@dataclass(frozen=True)
class RagHit:
    domain: str
    score: float
    title: str
    text: str
    source_uri: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RagSearchResult:
    domain: str
    query: str
    filters: dict[str, Any]
    hits: list[RagHit]
    elapsed_ms: float
    cached: bool = False


@dataclass(frozen=True)
class RagRouteResult:
    query: str
    intent: str
    domains: list[str]
    confidence: float
    filters: dict[str, Any]
    scores: dict[str, float]
    searches: list[RagSearchResult]
    elapsed_ms: float
    cached: bool = False


class TTLCache:
    def __init__(self, max_size: int = 128, ttl_seconds: float = 300.0) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        created, value = item
        if time.monotonic() - created > self.ttl_seconds:
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        self._items[key] = (time.monotonic(), value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)


class ModuleRagClient:
    _shared_store: Any | None = None
    _shared_router: Any | None = None
    _cache = TTLCache()

    def __init__(self, top_k: int = 5, cache_enabled: bool = True) -> None:
        self.top_k = top_k
        self.cache_enabled = cache_enabled

    def search(self, domain: str, query: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [self._hit_to_dict(hit) for hit in self.search_domain(domain, query, filters).hits]

    def search_domain(self, domain: str, query: str, filters: dict[str, Any] | None = None) -> RagSearchResult:
        started = time.monotonic()
        normalized_domain = self._domain(domain)
        normalized_filters = self._normalize_filters(filters or {})
        key = self._cache_key("search", normalized_domain, query, normalized_filters, self.top_k)
        if self.cache_enabled:
            cached = self._cache.get(key)
            if cached is not None:
                return RagSearchResult(
                    domain=cached.domain,
                    query=cached.query,
                    filters=cached.filters,
                    hits=cached.hits,
                    elapsed_ms=0.0,
                    cached=True,
                )

        raw_hits = self._store().search(normalized_domain, query, top_k=self.top_k, filters=normalized_filters)
        result = RagSearchResult(
            domain=normalized_domain,
            query=query,
            filters=normalized_filters,
            hits=[self._normalize_hit(normalized_domain, hit) for hit in raw_hits],
            elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        )
        if self.cache_enabled:
            self._cache.set(key, result)
        return result

    def route(self, query: str, memory_context: dict[str, Any] | None = None, agent_role: str = "default") -> RagRouteResult:
        started = time.monotonic()
        key = self._cache_key("route", query, memory_context or {}, agent_role, self.top_k)
        if self.cache_enabled:
            cached = self._cache.get(key)
            if cached is not None:
                cached_searches = [
                    RagSearchResult(
                        domain=search.domain,
                        query=search.query,
                        filters=search.filters,
                        hits=search.hits,
                        elapsed_ms=0.0,
                        cached=True,
                    )
                    for search in cached.searches
                ]
                return RagRouteResult(
                    query=cached.query,
                    intent=cached.intent,
                    domains=cached.domains,
                    confidence=cached.confidence,
                    filters=cached.filters,
                    scores=cached.scores,
                    searches=cached_searches,
                    elapsed_ms=0.0,
                    cached=True,
                )

        plan = self._router().route(query, memory_context=memory_context, agent_role=agent_role)
        domains = [self._domain(domain) for domain in plan.selected_domains]
        searches = [self.search_domain(domain, plan.query, plan.filters) for domain in domains]
        confidence = max((plan.scores.get(domain, 0.0) for domain in plan.selected_domains), default=0.0)
        result = RagRouteResult(
            query=plan.query,
            intent=plan.intent,
            domains=domains,
            confidence=confidence,
            filters=plan.filters,
            scores=plan.scores,
            searches=searches,
            elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        )
        if self.cache_enabled:
            self._cache.set(key, result)
        return result

    def investigate(
        self,
        primary_domain: str,
        query: str,
        filters: dict[str, Any] | None = None,
        related_domains: Iterable[str] = DEFAULT_DOMAINS,
    ) -> dict[str, Any]:
        started = time.monotonic()
        primary = self.search_domain(primary_domain, query, filters)
        related = []
        for domain in related_domains:
            normalized = self._domain(domain)
            if normalized == primary.domain:
                continue
            related.append(self.search_domain(normalized, query, filters))
        route = self.route(query)
        return {
            "query": query,
            "primary_domain": primary.domain,
            "route": self._route_summary(route),
            "primary": self._search_to_dict(primary),
            "related": [self._search_to_dict(result) for result in related],
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
            "cache": {
                "primary_cached": primary.cached,
                "route_cached": route.cached,
                "related_cached": {result.domain: result.cached for result in related},
            },
        }

    def format_cli(self, payload: dict[str, Any] | RagSearchResult | RagRouteResult) -> str:
        if isinstance(payload, RagSearchResult):
            return self._format_search(self._search_to_dict(payload))
        if isinstance(payload, RagRouteResult):
            return self._format_route(self._route_to_dict(payload))
        if "primary" in payload:
            return self._format_investigation(payload)
        if "searches" in payload:
            return self._format_route(payload)
        if "hits" in payload:
            return self._format_search(payload)
        return json.dumps(payload, indent=2, ensure_ascii=False, default=str)

    def _format_investigation(self, payload: dict[str, Any]) -> str:
        lines = [
            f"Query: {payload.get('query', '')}",
            f"Primary: {payload.get('primary_domain', '')}",
            f"Latency: {payload.get('elapsed_ms', 0)} ms",
            "",
            "Route:",
            json.dumps(payload.get("route", {}), indent=2, ensure_ascii=False),
            "",
            self._format_search(payload["primary"]),
        ]
        related = payload.get("related") or []
        if related:
            lines.extend(["", "Related RAG:"])
            for item in related:
                lines.append(self._format_search(item, max_hits=2))
        return "\n".join(lines)

    def _format_route(self, payload: dict[str, Any]) -> str:
        lines = [
            f"Query: {payload.get('query', '')}",
            f"Intent: {payload.get('intent', '')}",
            f"Domains: {', '.join(payload.get('domains', []))}",
            f"Confidence: {payload.get('confidence', 0):.2f}",
            f"Latency: {payload.get('elapsed_ms', 0)} ms",
        ]
        for search in payload.get("searches", []):
            lines.extend(["", self._format_search(search, max_hits=3)])
        return "\n".join(lines)

    def _format_search(self, payload: dict[str, Any], max_hits: int = 5) -> str:
        hits = payload.get("hits", [])
        lines = [
            f"[{payload.get('domain', '')}] {payload.get('query', '')}",
            f"hits={len(hits)} cached={payload.get('cached', False)} latency={payload.get('elapsed_ms', 0)} ms",
        ]
        if payload.get("filters"):
            lines.append(f"filters={json.dumps(payload['filters'], ensure_ascii=False)}")
        for index, hit in enumerate(hits[:max_hits], start=1):
            title = hit.get("title") or hit.get("source_uri") or "untitled"
            score = float(hit.get("score") or 0.0)
            text = " ".join(str(hit.get("text") or "").split())[:280]
            lines.append(f"{index}. score={score:.3f} {title}")
            if text:
                lines.append(f"   {text}")
        if not hits:
            lines.append("no results")
        return "\n".join(lines)

    def _store(self) -> Any:
        if self.__class__._shared_store is None:
            from rag.shared.embedding import EmbeddingService
            from rag.shared.qdrant_client import QdrantVectorStore

            self.__class__._shared_store = QdrantVectorStore(EmbeddingService())
        return self.__class__._shared_store

    def _router(self) -> Any:
        if self.__class__._shared_router is None:
            from rag.router import RagRouter

            self.__class__._shared_router = RagRouter()
        return self.__class__._shared_router

    def _normalize_hit(self, domain: str, hit: dict[str, Any]) -> RagHit:
        metadata = dict(hit)
        text = str(metadata.pop("text", "") or "")
        title = str(metadata.pop("title", "") or metadata.get("heading", "") or metadata.get("chunk_id", "") or "")
        source_uri = str(metadata.pop("source_uri", "") or metadata.get("path", "") or "")
        score = float(metadata.pop("score", 0.0) or 0.0)
        metadata.pop("domain", None)
        return RagHit(domain=domain, score=score, title=title, text=text, source_uri=source_uri, metadata=metadata)

    def _search_to_dict(self, result: RagSearchResult) -> dict[str, Any]:
        return {
            "domain": result.domain,
            "query": result.query,
            "filters": result.filters,
            "hits": [self._hit_to_dict(hit) for hit in result.hits],
            "elapsed_ms": result.elapsed_ms,
            "cached": result.cached,
        }

    def _route_to_dict(self, result: RagRouteResult) -> dict[str, Any]:
        return {
            "query": result.query,
            "intent": result.intent,
            "domains": result.domains,
            "confidence": result.confidence,
            "filters": result.filters,
            "scores": result.scores,
            "searches": [self._search_to_dict(search) for search in result.searches],
            "elapsed_ms": result.elapsed_ms,
            "cached": result.cached,
        }

    def _route_summary(self, result: RagRouteResult) -> dict[str, Any]:
        return {
            "intent": result.intent,
            "domains": result.domains,
            "confidence": result.confidence,
            "filters": result.filters,
            "scores": result.scores,
            "cached": result.cached,
        }

    def _hit_to_dict(self, hit: RagHit) -> dict[str, Any]:
        return asdict(hit)

    def _normalize_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in filters.items():
            if value in (None, "", [], ()):
                continue
            normalized[key] = value if isinstance(value, list) else [value]
        return normalized

    def _domain(self, domain: str) -> str:
        return DOMAIN_ALIASES.get(domain, domain)

    def _cache_key(self, *parts: Any) -> str:
        return json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
