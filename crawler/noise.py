"""Anti-noise filters for autonomous crawling."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlparse

NOISE_PATH_PARTS = (
    "/login",
    "/logout",
    "/signup",
    "/register",
    "/cart",
    "/checkout",
    "/privacy",
    "/terms",
    "/tag/",
    "/tags/",
    "/category/",
    "/author/",
    "/page/",
    "/feed",
    "/rss",
)

NOISE_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".zip",
    ".gz",
    ".tar",
    ".7z",
    ".exe",
    ".dll",
    ".dmg",
    ".iso",
    ".mp4",
    ".mp3",
)

BOILERPLATE_TERMS = (
    "cookie policy",
    "accept cookies",
    "subscribe to our newsletter",
    "enable javascript",
    "advertisement",
    "all rights reserved",
)


def should_fetch_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    lower_path = parsed.path.lower()
    if any(lower_path.endswith(extension) for extension in NOISE_EXTENSIONS):
        return False
    if any(part in lower_path for part in NOISE_PATH_PARTS):
        return False
    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=False)}
    if len(query_keys) > 8:
        return False
    if {"replytocom", "share", "print"} & query_keys:
        return False
    return True


def clean_text(text: str) -> str:
    cleaned = str(text or "")
    cleaned = re.sub(r"\b(cookie|subscribe|newsletter|advertisement|privacy policy|terms of use)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def is_noise_content(text: str) -> bool:
    cleaned = clean_text(text)
    lower = cleaned.lower()
    if len(cleaned) < 300:
        return True
    if any(term in lower for term in BOILERPLATE_TERMS) and len(cleaned) < 1200:
        return True
    tokens = re.findall(r"[a-zA-Z0-9_.:-]{3,}", lower)
    if not tokens:
        return True
    unique_ratio = len(set(tokens)) / max(1, len(tokens))
    if unique_ratio < 0.12:
        return True
    technical_hits = len(
        {
            token
            for token in tokens
            if token in {"cve", "exploit", "malware", "osint", "pentest", "github", "detection", "api", "yara", "sigma"}
        }
    )
    return technical_hits == 0 and len(tokens) < 800


__all__ = ["clean_text", "is_noise_content", "should_fetch_url"]

