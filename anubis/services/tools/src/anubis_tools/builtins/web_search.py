from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from anubis_tools.core.schemas import ToolDefinition


class WebSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=5, ge=1, le=10)


class WebSearchTool:
    definition = ToolDefinition(
        name="web.search",
        description="Mock web search interface. Replace with a provider-backed implementation.",
        input_schema=WebSearchInput.model_json_schema(),
        output_schema={
            "type": "object",
            "properties": {"results": {"type": "array"}},
            "required": ["results"],
        },
    )

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        request = WebSearchInput.model_validate(arguments)
        return {
            "results": [
                {
                    "title": f"Search result for {request.query}",
                    "url": "https://example.invalid/anubis/mock-search",
                    "snippet": "Mocked search result. Configure a real provider before production use.",
                }
            ][: request.limit]
        }
