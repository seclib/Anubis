from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from anubis_tools.core.schemas import ToolDefinition


class MemoryRetrieverInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class MemoryRetrieverTool:
    definition = ToolDefinition(
        name="memory.retrieve",
        description="Retrieves relevant memory references through the host RAG service.",
        input_schema=MemoryRetrieverInput.model_json_schema(),
        output_schema={"type": "object", "properties": {"memories": {"type": "array"}}},
    )

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        request = MemoryRetrieverInput.model_validate(arguments)
        return {"memories": [], "query": request.query, "limit": request.limit}
