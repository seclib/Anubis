from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(*parts: object) -> str:
    return sha256("::".join(str(part) for part in parts if part is not None).encode("utf-8")).hexdigest()


def clean_text(value: object, *, max_length: int | None = None) -> str:
    text = " ".join(str(value or "").split())
    return text[:max_length] if max_length else text
