from __future__ import annotations

import math

from anubis_rag.models.documents import RetrievedChunk
from anubis_rag.security.models import ChunkScore, SecurityFilterResult


class ChunkScoringEngine:
    def score(self, chunk: RetrievedChunk, security: SecurityFilterResult) -> ChunkScore:
        relevance_score = self._clamp(chunk.relevance_score)
        trust_score = self._source_trust(chunk)
        injection_risk_score = self._injection_risk(security)

        if not security.safe:
            trust_score *= math.exp(-0.35 * max(1, len(security.detected_patterns)))

        final_score = self._clamp((relevance_score * 0.4) + (trust_score * 0.4) - (injection_risk_score * 0.2))
        trust_level = "high" if final_score >= 0.75 and security.safe else "medium" if final_score >= 0.45 else "low"
        return ChunkScore(
            relevance_score=relevance_score,
            trust_score=self._clamp(trust_score),
            injection_risk_score=injection_risk_score,
            freshness_score=None,
            final_score=final_score,
            trust_level=trust_level,
        )

    def _source_trust(self, chunk: RetrievedChunk) -> float:
        source_type = str(chunk.metadata.get("source_type", "unknown"))
        if source_type == "note":
            return 0.9
        if source_type == "markdown":
            return 0.8
        if source_type == "text":
            return 0.65
        return 0.45

    def _injection_risk(self, security: SecurityFilterResult) -> float:
        if security.safe:
            return 0.0
        base = 0.3 + (0.15 * len(security.detected_patterns))
        if security.risk_type in {"tool_manipulation", "system_override"}:
            base += 0.25
        return self._clamp(base)

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))
