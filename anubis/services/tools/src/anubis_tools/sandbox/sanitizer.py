from __future__ import annotations

import hashlib
import json
from typing import Any

SENSITIVE_KEYS = {"api_key", "token", "secret", "password", "authorization", "cookie", "set-cookie"}


class OutputSanitizer:
    def __init__(self, max_output_bytes: int = 64000) -> None:
        self._max_output_bytes = max_output_bytes

    def sanitize(self, value: Any) -> dict[str, Any]:
        sanitized = self._sanitize_value(value)
        encoded = json.dumps(sanitized, ensure_ascii=True, sort_keys=True).encode("utf-8")
        if len(encoded) <= self._max_output_bytes:
            return sanitized if isinstance(sanitized, dict) else {"value": sanitized}
        truncated = encoded[: self._max_output_bytes].decode("utf-8", errors="replace")
        return {"truncated": True, "content": truncated}

    def output_hash(self, value: Any) -> str:
        encoded = json.dumps(value, ensure_ascii=True, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else self._sanitize_value(item)
                for key, item in value.items()
                if not self._is_system_metadata(key)
            }
        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        if isinstance(value, str):
            return value.replace("\x00", "").replace("\r", "\n")
        return value

    def _is_system_metadata(self, key: str) -> bool:
        lowered = key.lower()
        return lowered in {"absolute_path", "host_path", "cwd", "environment"} or lowered.startswith("_")
