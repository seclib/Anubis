"""Markdown parser for Obsidian notes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from knowledge.vault_scanner import VaultNote


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_/-]+)")
ENTITY_RE = re.compile(r"\b(?:CVE-\d{4}-\d{4,}|T\d{4}(?:\.\d{3})?|[A-Z][A-Za-z0-9_.-]{3,})\b")


@dataclass
class ParsedNote:
    note: VaultNote
    title: str
    body: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    headings: list[str] = field(default_factory=list)
    backlinks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)


class MarkdownParser:
    def parse(self, note: VaultNote) -> ParsedNote:
        text = note.text.replace("\r\n", "\n")
        frontmatter: dict[str, Any] = {}
        match = FRONTMATTER_RE.match(text)
        body = text
        if match:
            frontmatter = self._parse_frontmatter(match.group(1))
            body = text[match.end():]
        headings = [heading.strip() for _, heading in HEADING_RE.findall(body)]
        title = str(frontmatter.get("title") or "").strip()
        if not title:
            title = headings[0] if headings else note.path.stem
        backlinks = list(dict.fromkeys(link.strip() for link in WIKILINK_RE.findall(body) if link.strip()))
        tags = list(dict.fromkeys([*self._frontmatter_tags(frontmatter), *TAG_RE.findall(body)]))
        entities = list(dict.fromkeys(entity.strip() for entity in ENTITY_RE.findall(body) if entity.strip()))[:100]
        return ParsedNote(
            note=note,
            title=title[:220],
            body=body.strip(),
            frontmatter=frontmatter,
            headings=headings[:100],
            backlinks=backlinks[:100],
            tags=tags[:100],
            entities=entities,
        )

    def _parse_frontmatter(self, raw: str) -> dict[str, Any]:
        data: dict[str, Any] = {}
        current_key: str | None = None
        for line in raw.splitlines():
            if not line.strip():
                continue
            if line.startswith("  - ") and current_key:
                data.setdefault(current_key, [])
                if isinstance(data[current_key], list):
                    data[current_key].append(line[4:].strip())
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            if not value:
                data[current_key] = []
            elif value.startswith("[") and value.endswith("]"):
                data[current_key] = [part.strip().strip("'\"") for part in value[1:-1].split(",") if part.strip()]
            else:
                data[current_key] = value.strip("'\"")
        return data

    def _frontmatter_tags(self, frontmatter: dict[str, Any]) -> list[str]:
        tags = frontmatter.get("tags") or []
        if isinstance(tags, str):
            return [tag.strip().lstrip("#") for tag in tags.split(",") if tag.strip()]
        if isinstance(tags, list):
            return [str(tag).strip().lstrip("#") for tag in tags if str(tag).strip()]
        return []


__all__ = ["MarkdownParser", "ParsedNote"]

