from __future__ import annotations

import httpx

from anubis_ai_core.models.chat import RagSource


class RagClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)

    async def search(self, query: str, request_id: str, limit: int = 5) -> list[RagSource]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/search",
                headers={"x-request-id": request_id},
                json={"query": query, "limit": limit},
            )
            response.raise_for_status()
            payload = response.json()
        return [RagSource.model_validate(item) for item in payload.get("results", [])]
