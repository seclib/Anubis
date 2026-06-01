"""Knowledge gap detection."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


ENTITY_RE = re.compile(r"\b(?:CVE-\d{4}-\d{4,}|T\d{4}(?:\.\d{3})?|[A-Z][A-Za-z0-9_.-]{3,})\b")


class KnowledgeGapDetector:
    def detect(self, notes: list[Any]) -> list[dict[str, Any]]:
        titles = {note.title.lower() for note in notes}
        entity_counts: Counter[str] = Counter()
        low_source_notes: list[dict[str, Any]] = []
        no_synthesis_topics: Counter[str] = Counter()
        for note in notes:
            for entity in ENTITY_RE.findall(note.text):
                entity_counts[entity] += 1
            lower = note.text.lower()
            if len(note.text) > 800 and "source:" not in lower and "source_url:" not in lower:
                low_source_notes.append({"type": "weak_evidence", "note": str(note.path), "priority": 0.55})
            for topic in ("malware", "osint", "pentest", "vulnerability", "detection", "github"):
                if topic in lower:
                    no_synthesis_topics[topic] += 1
        gaps: list[dict[str, Any]] = []
        for entity, count in entity_counts.most_common(50):
            if count >= 2 and entity.lower() not in titles:
                gaps.append({"type": "missing_entity_note", "entity": entity, "mentions": count, "priority": min(1.0, 0.4 + count / 10)})
        synthesis_titles = {title for title in titles if "synthesis" in title or "overview" in title}
        for topic, count in no_synthesis_topics.items():
            if count >= 4 and not any(topic in title for title in synthesis_titles):
                gaps.append({"type": "missing_synthesis", "topic": topic, "mentions": count, "priority": min(1.0, 0.5 + count / 20)})
        gaps.extend(low_source_notes[:25])
        gaps.sort(key=lambda item: float(item.get("priority") or 0.0), reverse=True)
        return gaps[:100]


__all__ = ["KnowledgeGapDetector"]
