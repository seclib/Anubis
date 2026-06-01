"""Score fusion helpers for hybrid retrieval."""

from __future__ import annotations

from typing import Any


def reciprocal_rank_fusion(result_sets: list[list[dict[str, Any]]], k: int = 60) -> list[dict[str, Any]]:
    fused: dict[str, dict[str, Any]] = {}
    for result_set in result_sets:
        for rank, item in enumerate(result_set, start=1):
            key = str(item.get("source") or item.get("id") or item.get("text", "")[:120])
            if not key.strip():
                continue
            existing = fused.setdefault(key, {**item, "rrf_score": 0.0, "channels": []})
            existing["rrf_score"] = float(existing.get("rrf_score") or 0.0) + (1.0 / (k + rank))
            channels = existing.setdefault("channels", [])
            backend = item.get("backend")
            if backend and backend not in channels:
                channels.append(backend)
            existing["score"] = max(float(existing.get("score") or 0.0), float(item.get("score") or 0.0))
    results = list(fused.values())
    for item in results:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        trust = float(payload.get("trust_score") or payload.get("source_trust") or 0.0)
        quality = float(payload.get("quality_score") or 0.0)
        freshness = float(payload.get("freshness_score") or 0.0)
        entity_boost = 0.05 if payload.get("entities") else 0.0
        item["final_score"] = round(
            0.55 * float(item.get("rrf_score") or 0.0)
            + 0.25 * float(item.get("score") or 0.0)
            + 0.08 * trust
            + 0.06 * quality
            + 0.03 * freshness
            + entity_boost,
            6,
        )
    results.sort(key=lambda item: float(item.get("final_score") or 0.0), reverse=True)
    return results


__all__ = ["reciprocal_rank_fusion"]

