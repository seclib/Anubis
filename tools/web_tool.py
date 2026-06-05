from __future__ import annotations


class WebTool:
    """Simulation-first web search/fetch tool."""

    def execute(self, input: dict) -> dict:
        action = str(input.get("action", "")).strip().lower()
        if action == "search":
            return self._search(input)
        if action == "fetch":
            return self._fetch(input)
        return {"ok": False, "error": f"unknown web action: {action}"}

    def _search(self, input: dict) -> dict:
        query = str(input.get("query", "")).strip()
        return {
            "ok": True,
            "action": "search",
            "mode": "mock",
            "query": query,
            "results": [
                {
                    "title": f"Mock result for {query or 'query'}",
                    "url": "https://example.com/anubis/search-result",
                    "summary": "Simulated search result ready for real provider integration.",
                }
            ],
        }

    def _fetch(self, input: dict) -> dict:
        url = str(input.get("url", "")).strip()
        return {
            "ok": True,
            "action": "fetch",
            "mode": "mock",
            "url": url,
            "content": f"Simulated fetched content from {url or 'unknown URL'}.",
        }


__all__ = ["WebTool"]
