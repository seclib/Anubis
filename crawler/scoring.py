"""Deterministic content and URL scoring."""

from __future__ import annotations

import re
from urllib.parse import urlparse


TECHNICAL_TERMS = {
    "cve",
    "exploit",
    "malware",
    "osint",
    "pentest",
    "yara",
    "sigma",
    "ioc",
    "indicator",
    "mitre",
    "attack",
    "payload",
    "vulnerability",
    "github",
    "repository",
    "detection",
    "forensics",
    "reverse",
    "command",
    "api",
}

TRUSTED_HOST_MARKERS = (
    "github.com",
    "mitre.org",
    "nist.gov",
    "cisa.gov",
    "sans.org",
    "elastic.co",
    "microsoft.com",
    "googleprojectzero.blogspot.com",
)


def source_trust(url: str) -> float:
    host = urlparse(url).netloc.lower()
    if any(marker in host for marker in TRUSTED_HOST_MARKERS):
        return 0.9
    if host.endswith(".gov") or host.endswith(".edu"):
        return 0.85
    if "blog" in host or "research" in host:
        return 0.65
    return 0.45


def quality_score(text: str, url: str = "") -> float:
    lower = str(text or "").lower()
    if len(lower) < 300:
        return 0.0
    tokens = re.findall(r"[a-z0-9_.:-]{3,}", lower)
    if not tokens:
        return 0.0
    term_hits = sum(1 for term in TECHNICAL_TERMS if term in lower)
    code_boost = 0.12 if ("```" in text or "$ " in text or "curl " in lower) else 0.0
    entity_boost = 0.12 if re.search(r"\bCVE-\d{4}-\d{4,}\b|\bT\d{4}(?:\.\d{3})?\b", text, re.I) else 0.0
    density = min(1.0, term_hits / 8.0)
    length_score = min(1.0, len(tokens) / 1200.0)
    score = 0.45 * density + 0.20 * length_score + 0.20 * source_trust(url) + code_boost + entity_boost
    return round(min(1.0, score), 6)


def url_priority(url: str, query: str = "") -> float:
    lower_url = url.lower()
    query_terms = {term for term in re.findall(r"[a-z0-9_.:-]{3,}", query.lower())}
    url_hits = sum(1 for term in query_terms if term in lower_url)
    noise = 0.25 if any(part in lower_url for part in ("/tag/", "/category/", "/login", "utm_", "/page/")) else 0.0
    return round(max(0.0, 0.55 * source_trust(url) + 0.10 * url_hits - noise), 6)


__all__ = ["quality_score", "source_trust", "url_priority"]

