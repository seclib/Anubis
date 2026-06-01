"""HTML/text parser for crawler fetches."""

from __future__ import annotations

import html
import re
from urllib.parse import urljoin


def parse_html(url: str, content: str) -> dict[str, object]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", content, flags=re.I | re.S)
    title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else url
    links = [
        urljoin(url, html.unescape(match))
        for match in re.findall(r'href=["\']([^"\']+)["\']', content, flags=re.I)
        if match and not match.startswith(("#", "mailto:", "javascript:"))
    ]
    text = re.sub(r"<(script|style|noscript).*?</\1>", " ", content, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\b(cookie|subscribe|newsletter|advertisement|privacy policy|terms of use)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return {"title": title[:220], "text": text, "links": links[:200]}


__all__ = ["parse_html"]

