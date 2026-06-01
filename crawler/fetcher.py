"""Async HTTP fetcher with bounded bandwidth and SSRF-safe defaults."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx


MAX_BYTES = 2_000_000


def _is_private_host(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except Exception:
        return True
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return True
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return True
    return False


async def fetch_url(client: httpx.AsyncClient, url: str) -> dict[str, object]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"url": url, "error": "invalid http(s) url"}
    if _is_private_host(parsed.hostname or ""):
        return {"url": url, "error": "blocked private or unresolved host"}
    try:
        async with client.stream("GET", url, follow_redirects=True) as response:
            content_type = response.headers.get("content-type", "")
            if not any(kind in content_type.lower() for kind in ("text/html", "text/plain", "markdown", "json", "xml", "")):
                return {"url": str(response.url), "status_code": response.status_code, "error": f"unsupported content type {content_type}"}
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_BYTES:
                    return {"url": str(response.url), "status_code": response.status_code, "error": "response too large"}
                chunks.append(chunk)
            text = b"".join(chunks).decode(response.encoding or "utf-8", errors="ignore")
            return {"url": str(response.url), "status_code": response.status_code, "content_type": content_type, "text": text}
    except Exception as exc:
        return {"url": url, "error": str(exc)}


__all__ = ["fetch_url"]

