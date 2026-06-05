from __future__ import annotations

import os
from dataclasses import dataclass


DOMAINS = ("osint", "cve", "bugbounty", "dev", "cyberdefense")


@dataclass(frozen=True)
class RouterConfig:
    qdrant_url: str = os.getenv("ANUBIS_QDRANT_URL", "http://localhost:6333")
    embedding_model: str = os.getenv("ANUBIS_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    default_top_k: int = int(os.getenv("ANUBIS_RAG_TOP_K", "6"))
    primary_threshold: float = float(os.getenv("ANUBIS_PRIMARY_ROUTE_THRESHOLD", "0.72"))
    secondary_threshold: float = float(os.getenv("ANUBIS_SECONDARY_ROUTE_THRESHOLD", "0.50"))
    fallback_threshold: float = float(os.getenv("ANUBIS_FALLBACK_ROUTE_THRESHOLD", "0.35"))
    collection_prefix: str = os.getenv("ANUBIS_COLLECTION_PREFIX", "anubis")


config = RouterConfig()


def collection_name(domain: str) -> str:
    return f"{config.collection_prefix}_{domain}_chunks"
