"""URL and content deduplication helpers."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


def normalize_url(url: str) -> str:
    parsed = urlparse(str(url).strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_pairs))
    return urlunparse((scheme, netloc, path.rstrip("/") or "/", "", query, ""))


def content_hash(text: str) -> str:
    normalized = " ".join(str(text or "").split()).lower()
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()


class DedupeLedger:
    def __init__(self) -> None:
        self.urls: set[str] = set()
        self.hashes: set[str] = set()

    def seen_url(self, url: str) -> bool:
        normalized = normalize_url(url)
        if normalized in self.urls:
            return True
        self.urls.add(normalized)
        return False

    def seen_content(self, text: str) -> bool:
        digest = content_hash(text)
        if digest in self.hashes:
            return True
        self.hashes.add(digest)
        return False


__all__ = ["DedupeLedger", "content_hash", "normalize_url"]

