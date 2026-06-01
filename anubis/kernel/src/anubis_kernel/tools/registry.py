from __future__ import annotations

from anubis_kernel.tools.schemas import RegisteredTool, ToolDefinition


async def web_search(parameters: dict) -> dict:
    query = str(parameters["query"])
    return {"summary": f"search completed for {query}", "results": [{"title": query, "url": "https://example.invalid"}]}


async def memory_retrieve(parameters: dict) -> dict:
    query = str(parameters["query"])
    return {"summary": f"memory retrieval completed for {query}", "memories": []}


def create_registry() -> dict[str, RegisteredTool]:
    return {
        "web_search": RegisteredTool(
            definition=ToolDefinition(
                name="web_search",
                parameters_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 500}},
                },
            ),
            executor=web_search,
        ),
        "memory_retrieve": RegisteredTool(
            definition=ToolDefinition(
                name="memory_retrieve",
                parameters_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 500}},
                },
            ),
            executor=memory_retrieve,
        ),
    }
