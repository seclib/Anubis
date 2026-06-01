from __future__ import annotations

from anubis_rag.models.documents import RetrievedChunk
from anubis_rag.security.filter import SecurityFilter
from anubis_rag.security.models import SafeContextResponse, SafeContextSource, SecuredChunk
from anubis_rag.security.sanitizer import RagInputSanitizer
from anubis_rag.security.scoring import ChunkScoringEngine
from anubis_rag.security.transformer import ContextTransformer


class SecureRagPipeline:
    def __init__(self) -> None:
        self._sanitizer = RagInputSanitizer()
        self._filter = SecurityFilter()
        self._scoring = ChunkScoringEngine()
        self._transformer = ContextTransformer()

    def sanitize_query(self, query: str) -> str:
        return self._sanitizer.sanitize_query(query)

    def secure_chunks(self, chunks: list[RetrievedChunk]) -> list[SecuredChunk]:
        secured: list[SecuredChunk] = []
        for chunk in chunks:
            safe_text = self._sanitizer.sanitize_chunk_text(chunk.text)
            sanitized_chunk = chunk.model_copy(update={"text": safe_text})
            security = self._filter.inspect(safe_text)
            score = self._scoring.score(sanitized_chunk, security)
            transformed = self._transformer.transform(safe_text, security, score.trust_level)
            secured.append(
                SecuredChunk(
                    chunk=sanitized_chunk,
                    security=security,
                    score=score,
                    transformed=transformed,
                    allowed_for_prompt=score.trust_level != "low" or bool(transformed.facts),
                )
            )
        return secured

    def build_safe_context(self, chunks: list[RetrievedChunk]) -> SafeContextResponse:
        secured = self.secure_chunks(chunks)
        facts: list[str] = []
        high_trust_facts: list[str] = []
        low_trust_facts: list[str] = []
        warnings: list[str] = []
        sources: list[SafeContextSource] = []

        for item in secured:
            if not item.allowed_for_prompt:
                warnings.append(f"Excluded unsafe chunk {item.chunk.chunk_id}: {item.security.reason}")
                continue
            facts.extend(item.transformed.facts)
            warnings.extend(item.transformed.warnings)
            warnings.extend(item.transformed.removed_instructions)
            if item.score.trust_level == "high":
                high_trust_facts.extend(item.transformed.facts)
            if item.score.trust_level == "low":
                low_trust_facts.extend(item.transformed.facts)
            sources.append(
                SafeContextSource(
                    chunk_id=item.chunk.chunk_id,
                    document_id=item.chunk.document_id,
                    title=item.chunk.title,
                    final_score=item.score.final_score,
                    trust_level=item.score.trust_level,
                    risk_type=item.security.risk_type,
                )
            )

        facts = self._dedupe(facts)
        return SafeContextResponse(
            context_summary=self._summary(facts, warnings),
            facts=facts,
            high_trust_facts=self._dedupe(high_trust_facts),
            low_trust_facts=self._dedupe(low_trust_facts),
            warnings=self._dedupe(warnings),
            sources=sources,
        )

    def _summary(self, facts: list[str], warnings: list[str]) -> str:
        if not facts:
            return "No safe facts were extracted from retrieved context."
        warning_note = f" {len(warnings)} warning(s) were generated." if warnings else ""
        return f"Extracted {len(facts)} safe fact(s) from retrieved context.{warning_note}"

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            key = value.lower()
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result
