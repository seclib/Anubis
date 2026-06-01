from __future__ import annotations

import re
import unicodedata


class RagInputSanitizer:
    CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

    def sanitize_query(self, query: str) -> str:
        return self._sanitize(query, max_length=2000)

    def sanitize_chunk_text(self, text: str) -> str:
        return self._sanitize(text, max_length=12000)

    def _sanitize(self, value: str, *, max_length: int) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        normalized = self.CONTROL_CHARS.sub("", normalized)
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ \t]{2,}", " ", normalized)
        normalized = re.sub(r"\n{4,}", "\n\n\n", normalized)
        return normalized.strip()[:max_length]
