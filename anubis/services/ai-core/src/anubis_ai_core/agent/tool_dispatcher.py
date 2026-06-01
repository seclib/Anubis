from __future__ import annotations

from typing import Any

from anubis_tools import ToolRegistry

from anubis_ai_core.memory.interface import AgentMemoryInterface
from anubis_ai_core.models.agent import AgentToolResult, ToolCall


class ToolDispatcher:
    def __init__(self, *, registry: ToolRegistry, memory: AgentMemoryInterface, request_id: str) -> None:
        self._registry = registry
        self._memory = memory
        self._request_id = request_id

    async def dispatch(self, call: ToolCall) -> AgentToolResult:
        parameters = self._sanitize_parameters(call.parameters)
        try:
            if call.tool_name in {"rag_query", "memory_retrieve"}:
                query = str(parameters.get("query", "")).strip()
                limit = int(parameters.get("limit", 5))
                memories = await self._memory.retrieve(query, request_id=self._request_id, limit=limit)
                return AgentToolResult(
                    tool_name=call.tool_name,
                    status="succeeded",
                    output={"memories": [memory.model_dump(mode="json") for memory in memories]},
                )
            if call.tool_name == "memory_store":
                namespace = str(parameters.get("namespace", "agent"))
                content = str(parameters.get("content", "")).strip()
                if not content:
                    raise ValueError("memory_store requires content")
                output = await self._memory.store(namespace, {"content": content, "metadata": parameters.get("metadata", {})})
                return AgentToolResult(tool_name=call.tool_name, status="succeeded", output=output)

            registry_name = {
                "web_search": "web.search",
                "file_read": "file.read",
                "file_write": "note.write",
            }.get(call.tool_name)
            if registry_name is None:
                raise ValueError(f"Unsupported tool: {call.tool_name}")
            result = await self._registry.execute(registry_name, parameters)
            return AgentToolResult(
                tool_name=call.tool_name,
                status=result.status,
                output=self._sanitize_parameters(result.output),
                error=result.error,
            )
        except Exception as exc:  # noqa: BLE001 - tool boundary must convert failures to data.
            return AgentToolResult(tool_name=call.tool_name, status="failed", error=str(exc))

    def _sanitize_parameters(self, parameters: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in parameters.items():
            if key.lower() in {"api_key", "token", "secret", "password", "authorization"}:
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, str) and len(value) > 20000:
                sanitized[key] = value[:20000]
            else:
                sanitized[key] = value
        return sanitized
