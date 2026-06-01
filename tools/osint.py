"""OSINT helpers for opt-in background web intelligence collection."""

from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus, urlparse

import requests

TECHNICAL_KEYWORDS = {
    "api",
    "attack",
    "cve",
    "command",
    "detection",
    "exploit",
    "github",
    "indicator",
    "ioc",
    "mitigation",
    "osint",
    "pentest",
    "payload",
    "python",
    "research",
    "rule",
    "scanner",
    "sigma",
    "tool",
    "workflow",
    "yara",
}

SOURCE_TEMPLATES = (
    "https://api.github.com/search/repositories?q={query}+security+osint+pentest&sort=updated&order=desc&per_page=5",
    "https://api.github.com/search/code?q={query}+security+OR+osint+OR+pentest&per_page=5",
    "https://hn.algolia.com/api/v1/search?query={query}%20security&tags=story",
)


def fetch_external_data(url: str, timeout: int = 10, max_chars: int = 12000) -> dict[str, object]:
    """Fetch a public HTTP(S) resource and return bounded text content."""
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("fetch_external_data requires an absolute http(s) URL")

    bounded_timeout = max(1, min(int(timeout), 30))
    bounded_chars = max(1000, min(int(max_chars), 50000))
    response = requests.get(
        parsed.geturl(),
        timeout=bounded_timeout,
        headers={"User-Agent": "Anubis-OSINT/1.0"},
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    text = response.text[:bounded_chars]
    return {
        "url": response.url,
        "status_code": response.status_code,
        "content_type": content_type,
        "truncated": len(response.text) > bounded_chars,
        "text": text,
    }


def _strip_noise(text: str) -> str:
    cleaned = re.sub(r"<(script|style|noscript).*?</\1>", " ", text, flags=re.I | re.S)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\b(cookie|subscribe|newsletter|advertisement|privacy policy|terms of use)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _technical_lines(text: str, limit: int = 30) -> list[str]:
    cleaned = _strip_noise(text)
    candidates = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    lines: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        line = candidate.strip()
        if len(line) < 30:
            continue
        lower = line.lower()
        if not any(keyword in lower for keyword in TECHNICAL_KEYWORDS):
            continue
        key = lower[:160]
        if key in seen:
            continue
        seen.add(key)
        lines.append(line[:500])
        if len(lines) >= limit:
            break
    return lines


def _source_urls(query: str, seeds: list[str] | None = None, max_sources: int = 6) -> list[str]:
    urls: list[str] = []
    for seed in seeds or []:
        parsed = urlparse(str(seed).strip())
        if parsed.scheme in {"http", "https"} and parsed.netloc and seed not in urls:
            urls.append(seed)
    encoded = quote_plus(query.strip()[:120] or "cybersecurity osint")
    for template in SOURCE_TEMPLATES:
        url = template.format(query=encoded)
        if url not in urls:
            urls.append(url)
    return urls[: max(1, min(int(max_sources), 10))]


def _fetch_and_extract(url: str, timeout: int, max_chars: int) -> dict[str, object]:
    fetched = fetch_external_data(url=url, timeout=timeout, max_chars=max_chars)
    lines = _technical_lines(str(fetched.get("text") or ""))
    return {
        **fetched,
        "technical_lines": lines,
        "actionable": bool(lines),
    }


def crawl_osint_sources(
    query: str,
    seeds: list[str] | None = None,
    max_sources: int = 6,
    timeout: int = 10,
    max_chars: int = 12000,
) -> dict[str, object]:
    """Fetch multiple preferred OSINT/cyber sources in parallel and emit markdown notes."""
    sources = _source_urls(query, seeds=seeds, max_sources=max_sources)
    results: list[dict[str, object]] = []
    workers = min(6, len(sources))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_and_extract, url, max(1, min(int(timeout), 20)), max_chars): url
            for url in sources
        }
        for future in as_completed(futures):
            url = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"url": url, "success": False, "error": str(exc), "technical_lines": []})

    notes = []
    for result in results:
        lines = [str(line) for line in result.get("technical_lines", []) if str(line).strip()]
        if not lines:
            continue
        source = str(result.get("url") or "")
        title = f"OSINT crawler - {query[:80]} - {urlparse(source).netloc or 'source'}"
        note = (
            f"# {title}\n\n"
            "## Summary\n\n"
            f"- Query: {query}\n"
            f"- Source: {source}\n"
            f"- Status: {result.get('status_code', 'unknown')}\n"
            "- Extracted only technical/actionable lines; marketing and boilerplate omitted.\n\n"
            "## Tools\n\n"
            "- crawl_osint_sources\n"
            "- fetch_external_data\n\n"
            "## Commands\n\n"
            "```bash\n"
            f"curl -L {source}\n"
            "```\n\n"
            "## Workflow\n\n"
            "- Discover preferred source.\n"
            "- Fetch in parallel.\n"
            "- Filter for tools, commands, indicators, exploits, mitigations, APIs, and workflows.\n"
            "- Store as Obsidian markdown and index into Qdrant.\n\n"
            "## Technical Extract\n\n"
            + "\n".join(f"- {line}" for line in lines[:30])
            + "\n\n## RAG Notes\n\n"
            "- Reusable technical facts only.\n"
            "- Validate time-sensitive exploit/tool status before action.\n"
        )
        notes.append({"title": title, "content": note, "folder": "OSINT", "source": source})

    return {
        "query": query,
        "sources": sources,
        "results": results,
        "notes": notes,
        "notes_ready": len(notes),
    }


__all__ = ["crawl_osint_sources", "fetch_external_data"]
