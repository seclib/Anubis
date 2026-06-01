from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from anubis_tools.sandbox.schemas import AuditEvent


class ImmutableAuditLogger:
    def __init__(self, audit_log_path: Path) -> None:
        self._path = audit_log_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def append(
        self,
        *,
        request_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        status: str,
        duration_ms: float,
        output_hash: str,
        error_code: str | None,
    ) -> AuditEvent:
        async with self._lock:
            previous_hash = await asyncio.to_thread(self._last_hash)
            event_hash = self._event_hash(
                request_id=request_id,
                tool_name=tool_name,
                parameters=parameters,
                status=status,
                duration_ms=duration_ms,
                output_hash=output_hash,
                error_code=error_code,
                previous_hash=previous_hash,
            )
            event = AuditEvent(
                request_id=request_id,
                tool_name=tool_name,
                parameters=parameters,
                status=status,  # type: ignore[arg-type]
                duration_ms=duration_ms,
                output_hash=output_hash,
                error_code=error_code,
                previous_hash=previous_hash,
                event_hash=event_hash,
            )
            await asyncio.to_thread(self._append_sync, event)
            return event

    def _append_sync(self, event: AuditEvent) -> None:
        flags = "a"
        with self._path.open(flags, encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")

    def _last_hash(self) -> str:
        if not self._path.exists():
            return "0" * 64
        last = ""
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    last = line
        if not last:
            return "0" * 64
        try:
            return str(json.loads(last)["event_hash"])
        except (json.JSONDecodeError, KeyError):
            return "0" * 64

    def _event_hash(self, **payload: Any) -> str:
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
