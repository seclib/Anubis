from __future__ import annotations

import re

from anubis_rag.security.filter import SecurityFilter
from anubis_rag.security.models import SecurityFilterResult, TransformedContext, TrustLevel
from anubis_rag.security.sanitizer import RagInputSanitizer


class ContextTransformer:
    COMMAND_PATTERNS = (
        re.compile(r"\bignore\s+(all\s+)?(previous|prior)\s+instructions\b.*", re.I),
        re.compile(r"\bignore\s+(the\s+)?system\b.*", re.I),
        re.compile(r"\byou\s+are\s+now\b.*", re.I),
        re.compile(r"\bact\s+as\b.*", re.I),
        re.compile(r"\bsystem\s+prompt\b.*", re.I),
        re.compile(r"\bexecute\b.*", re.I),
        re.compile(r"\bcall\s+(the\s+)?tool\b.*", re.I),
        re.compile(r"\bdelete\s+(all\s+)?files\b.*", re.I),
        re.compile(r"\boverride\b.*", re.I),
        re.compile(r".*\"tool_name\"\s*:.*", re.I),
        re.compile(r"\b(store|save|remember)\s+this\s+(as\s+)?(permanent\s+)?memory\b.*", re.I),
    )

    ENTITY_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9_-]{2,}\b")

    def __init__(self) -> None:
        self._sanitizer = RagInputSanitizer()
        self._filter = SecurityFilter()

    def transform(self, raw_text: str, security: SecurityFilterResult, trust_level: TrustLevel) -> TransformedContext:
        text = self._sanitizer.sanitize_chunk_text(raw_text)
        facts: list[str] = []
        removed: list[str] = []
        warnings: list[str] = []

        for sentence in self._sentences(text):
            if self._is_instruction(sentence):
                removed.append(f"ignored instruction: {sentence[:240]}")
                fact = self._neutral_fact(sentence)
                if fact:
                    facts.append(fact)
                continue
            if self._filter.inspect(sentence).safe:
                facts.append(sentence)
            else:
                removed.append(f"ignored instruction-like text: {sentence[:240]}")

        if not security.safe:
            warnings.append(security.reason)
        if not facts and removed:
            facts.append("Document contains instruction-like content that was neutralized.")

        return TransformedContext(
            facts=self._dedupe(facts)[:12],
            entities=self._entities(text)[:20],
            warnings=warnings,
            removed_instructions=removed[:20],
            trust_level=trust_level,
        )

    def _sentences(self, text: str) -> list[str]:
        candidates = re.split(r"(?<=[.!?])\s+|\n+", text)
        return [candidate.strip(" -\t") for candidate in candidates if candidate.strip(" -\t")]

    def _is_instruction(self, sentence: str) -> bool:
        return any(pattern.search(sentence) for pattern in self.COMMAND_PATTERNS)

    def _neutral_fact(self, sentence: str) -> str | None:
        lowered = sentence.lower()
        if "delete" in lowered and "file" in lowered:
            return "Document contains a request related to file deletion."
        if "tool" in lowered:
            return "Document contains a request related to tool usage."
        if "system prompt" in lowered or "ignore" in lowered or "override" in lowered:
            return "Document contains text attempting to influence instructions."
        if "memory" in lowered or "remember" in lowered:
            return "Document contains text attempting to influence memory."
        return None

    def _entities(self, text: str) -> list[str]:
        return self._dedupe(self.ENTITY_PATTERN.findall(text))

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            key = value.lower()
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result
