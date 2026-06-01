"""Build compact citation-preserving retrieval contexts."""

from __future__ import annotations

from typing import Any


def build_context(results: list[dict[str, Any]], max_chars: int = 8000) -> str:
    blocks: list[str] = []
    used = 0
    seen_text: set[str] = set()
    for index, item in enumerate(results, start=1):
        text = str(item.get("text") or item.get("payload", {}).get("text") or "").strip()
        if not text:
            continue
        dedupe_key = text[:220].lower()
        if dedupe_key in seen_text:
            continue
        seen_text.add(dedupe_key)
        source = str(item.get("source") or item.get("payload", {}).get("source") or "unknown")
        title = str(item.get("payload", {}).get("title") or source)
        block = (
            f"[{index}] {title}\n"
            f"source: {source}\n"
            f"score: {item.get('final_score', item.get('score', 0))}\n"
            f"{text[:1600]}"
        )
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


__all__ = ["build_context"]

