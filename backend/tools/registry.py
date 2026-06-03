from __future__ import annotations

from typing import Any, Mapping

from backend.tools.base import BaseTool
from backend.tools.filesystem import ReadFileTool, WriteFileTool
from backend.tools.git import GitCommitTool, GitDiffTool
from backend.tools.search import SearchCodebaseTool
from backend.tools.shell import RunCommandTool


def build_tool_registry() -> dict[str, BaseTool]:
    tools: list[BaseTool] = [
        ReadFileTool(),
        WriteFileTool(),
        SearchCodebaseTool(),
        RunCommandTool(),
        GitDiffTool(),
        GitCommitTool(),
    ]
    return {tool.name: tool for tool in tools}


TOOLS = build_tool_registry()


def invoke_tool(tool: str, tool_input: Mapping[str, Any] | None = None) -> dict[str, Any]:
    selected = TOOLS.get(tool)
    input_data = dict(tool_input or {})
    if selected is None:
        return {
            "tool": tool,
            "input": input_data,
            "output": {
                "error": f"Unknown tool: {tool}",
                "type": "UnknownToolError",
            },
            "success": False,
        }
    return selected.invoke(input_data)


__all__ = ["TOOLS", "build_tool_registry", "invoke_tool"]
