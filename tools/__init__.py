"""System tool layer compatibility facade.

Keep package import side-effect free so runtime code can import individual
``tools.*`` modules even while the legacy ``anubis.*`` package layout is being
migrated.
"""

_EXPORTS = {
    "BaseTool": ("tools.base", "BaseTool"),
    "FilesystemTool": ("tools.filesystem_tool", "FilesystemTool"),
    "GitHubTool": ("tools.github_tool", "GitHubTool"),
    "ReadFileTool": ("tools.filesystem", "ReadFileTool"),
    "Tool": ("tools.interfaces", "Tool"),
    "ToolCallLogger": ("tools.logging", "ToolCallLogger"),
    "ToolError": ("tools.errors", "ToolError"),
    "ToolExecutionContext": ("tools.base", "ToolExecutionContext"),
    "ToolExecutionEngine": ("tools.engine", "ToolExecutionEngine"),
    "ToolExecutionError": ("tools.errors", "ToolExecutionError"),
    "ToolNotFoundError": ("tools.errors", "ToolNotFoundError"),
    "ToolRegistry": ("tools.registry", "ToolRegistry"),
    "ToolRouter": ("tools.tool_router", "ToolRouter"),
    "ToolSpec": ("tools.base", "ToolSpec"),
    "ToolValidationError": ("tools.errors", "ToolValidationError"),
    "WebTool": ("tools.web_tool", "WebTool"),
    "WriteFileTool": ("tools.filesystem", "WriteFileTool"),
    "create_default_tool_engine": ("tools.defaults", "create_default_tool_engine"),
    "filesystem_tools": ("tools.filesystem", "filesystem_tools"),
    "route_tool": ("tools.tool_router", "route_tool"),
}


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = __import__(module_name, fromlist=[attribute])
    value = getattr(module, attribute)
    globals()[name] = value
    return value

__all__ = [
    "BaseTool",
    "FilesystemTool",
    "GitHubTool",
    "ReadFileTool",
    "Tool",
    "ToolCallLogger",
    "ToolError",
    "ToolExecutionEngine",
    "ToolExecutionContext",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolRegistry",
    "ToolRouter",
    "ToolSpec",
    "ToolValidationError",
    "WebTool",
    "WriteFileTool",
    "create_default_tool_engine",
    "filesystem_tools",
    "route_tool",
]
