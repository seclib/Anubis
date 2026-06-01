"""Confidence scoring for grounded retrieval."""

from __future__ import annotations

from typing import Any


def retrieval_confidence(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {"score": 0.0, "level": "none", "reason": "no evidence retrieved"}
    scores = [float(item.get("final_score") or item.get("score") or 0.0) for item in results]
    top = scores[0]
    margin = max(0.0, top - (scores[1] if len(scores) > 1 else 0.0))
    sources = {str(item.get("source") or "") for item in results if item.get("source")}
    payloads = [item.get("payload") for item in results if isinstance(item.get("payload"), dict)]
    trust = sum(float(payload.get("trust_score") or payload.get("source_trust") or 0.0) for payload in payloads) / max(1, len(payloads))
    diversity = min(1.0, len(sources) / 4.0)
    score = min(1.0, 0.35 * min(1.0, top) + 0.20 * min(1.0, margin * 10) + 0.20 * trust + 0.25 * diversity)
    if score >= 0.7:
        level = "high"
    elif score >= 0.4:
        level = "medium"
    else:
        level = "low"
    return {"score": round(score, 6), "level": level, "source_diversity": len(sources), "top_score": round(top, 6)}


__all__ = ["retrieval_confidence"]

