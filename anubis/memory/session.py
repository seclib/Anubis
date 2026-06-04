from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionMemory:
    """Small local memory for Claude-Code-like terminal sessions."""

    transcript: list[dict[str, str]] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    tool_history: list[dict[str, Any]] = field(default_factory=list)
    max_transcript: int = 40
    max_facts: int = 80

    def add_message(self, role: str, content: str) -> None:
        clean = str(content).strip()
        if not clean:
            return
        self.transcript.append({"role": role, "content": clean})
        if len(self.transcript) > self.max_transcript:
            self.transcript = self.transcript[-self.max_transcript :]

    def remember(self, text: str) -> None:
        clean = " ".join(str(text).split())
        if not clean or clean in self.facts:
            return
        self.facts.append(clean)
        if len(self.facts) > self.max_facts:
            self.facts = self.facts[-self.max_facts :]

    def add_tool_result(self, result: dict[str, Any]) -> None:
        self.tool_history.append(dict(result))
        if len(self.tool_history) > 50:
            self.tool_history = self.tool_history[-50:]

    def retrieve(self, query: str, limit: int = 6) -> list[str]:
        terms = {part.lower() for part in query.split() if len(part) > 2}
        scored: list[tuple[int, str]] = []
        for fact in self.facts:
            lowered = fact.lower()
            score = sum(1 for term in terms if term in lowered)
            if score:
                scored.append((score, fact))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [fact for _, fact in scored[: max(1, limit)]]

    def compact(self) -> str:
        recent = self.transcript[-8:]
        lines = ["Recent transcript:"]
        lines.extend(f"- {item['role']}: {item['content']}" for item in recent)
        if self.facts:
            lines.append("Session facts:")
            lines.extend(f"- {fact}" for fact in self.facts[-12:])
        if self.tool_history:
            lines.append("Recent tools:")
            for result in self.tool_history[-8:]:
                lines.append(
                    f"- {result.get('tool', 'unknown')}: "
                    f"{'ok' if result.get('success') else 'failed'}"
                )
        return "\n".join(lines)


__all__ = ["SessionMemory"]
