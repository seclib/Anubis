"""Content extraction and Obsidian note rendering for crawler results."""

from __future__ import annotations

import re
from typing import Any

from crawler.noise import clean_text

ENTITY_RE = re.compile(r"\b(?:CVE-\d{4}-\d{4,}|T\d{4}(?:\.\d{3})?|[a-fA-F0-9]{32,64}|(?:\d{1,3}\.){3}\d{1,3})\b")


def extract_content(parsed: dict[str, Any], *, url: str, query: str) -> dict[str, Any]:
    text = clean_text(str(parsed.get("text") or ""))
    entities = list(dict.fromkeys(ENTITY_RE.findall(text)))[:80]
    technical_lines = _technical_lines(text)
    summary = technical_lines[:8] if technical_lines else [text[:500]]
    return {
        "title": str(parsed.get("title") or url).strip()[:220],
        "url": url,
        "query": query,
        "text": text,
        "entities": entities,
        "technical_lines": technical_lines,
        "summary": summary,
        "links": parsed.get("links", []),
    }


def render_obsidian_note(extracted: dict[str, Any], metadata: dict[str, Any]) -> str:
    title = str(extracted.get("title") or "OSINT Crawl Result")
    url = str(extracted.get("url") or "")
    query = str(extracted.get("query") or "")
    entities = [str(item) for item in extracted.get("entities", [])]
    lines = [str(item) for item in extracted.get("technical_lines", [])]
    tags = _tags(extracted)
    frontmatter_tags = "\n".join(f"  - {tag}" for tag in tags)
    entity_lines = "\n".join(f"- {entity}" for entity in entities[:40]) or "- None detected."
    technical = "\n".join(f"- {line}" for line in lines[:60]) or str(extracted.get("text") or "")[:4000]
    return (
        "---\n"
        "type: source\n"
        "source_type: osint\n"
        f"title: {title}\n"
        f"source_url: {url}\n"
        f"query: {query}\n"
        f"quality_score: {metadata.get('quality_score', 0)}\n"
        f"trust_score: {metadata.get('trust_score', 0)}\n"
        "tags:\n"
        f"{frontmatter_tags}\n"
        "---\n\n"
        f"# {title}\n\n"
        "## Source\n\n"
        f"- URL: {url}\n"
        f"- Query: {query}\n"
        f"- Status: {metadata.get('status_code', 'unknown')}\n\n"
        "## Entities\n\n"
        f"{entity_lines}\n\n"
        "## Technical Extract\n\n"
        f"{technical}\n\n"
        "## RAG Notes\n\n"
        "- Automatically extracted by Anubis crawler.\n"
        "- Validate time-sensitive exploitability before operational use.\n"
    )


def _technical_lines(text: str, limit: int = 80) -> list[str]:
    keywords = (
        "cve",
        "exploit",
        "malware",
        "osint",
        "pentest",
        "payload",
        "detection",
        "github",
        "api",
        "command",
        "yara",
        "sigma",
        "ioc",
        "mitre",
        "vulnerability",
    )
    candidates = re.split(r"(?<=[.!?])\s+|\n+", text)
    lines: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        line = candidate.strip()
        if len(line) < 40:
            continue
        lower = line.lower()
        if not any(keyword in lower for keyword in keywords):
            continue
        key = lower[:180]
        if key in seen:
            continue
        seen.add(key)
        lines.append(line[:800])
        if len(lines) >= limit:
            break
    return lines


def _tags(extracted: dict[str, Any]) -> list[str]:
    text = " ".join([str(extracted.get("title") or ""), str(extracted.get("text") or "")]).lower()
    tags = ["domain/osint", "source/crawler", "type/source"]
    if "malware" in text or "yara" in text:
        tags.append("domain/malware")
    if "cve" in text or "vulnerability" in text:
        tags.append("domain/vulnerability")
    if "pentest" in text or "exploit" in text:
        tags.append("domain/pentesting")
    if "github" in text or "api" in text:
        tags.append("domain/programming")
    return list(dict.fromkeys(tags))


__all__ = ["extract_content", "render_obsidian_note"]

