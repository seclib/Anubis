"""Plugin loading primitives for runtime-owned tool extensions.

Plugins may contribute additional tool callables, but they never import the
agent loop. Runtime owns discovery and registration, then passes a flat registry
to the isolated executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from executor.tool_executor import ToolFunction


@dataclass(frozen=True)
class ToolPlugin:
    name: str
    tools: Mapping[str, ToolFunction] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)


class PluginManager:
    """Collect runtime plugins into a deterministic tool registry."""

    def __init__(self, plugins: list[ToolPlugin] | None = None) -> None:
        self._plugins: list[ToolPlugin] = list(plugins or [])

    def register(self, plugin: ToolPlugin) -> None:
        existing = {item.name for item in self._plugins}
        if plugin.name in existing:
            raise ValueError(f"Plugin already registered: {plugin.name}")
        self._plugins.append(plugin)

    def tools(self) -> dict[str, ToolFunction]:
        registry: dict[str, ToolFunction] = {}
        for plugin in self._plugins:
            duplicate = set(registry).intersection(plugin.tools)
            if duplicate:
                names = ", ".join(sorted(duplicate))
                raise ValueError(f"Plugin {plugin.name} overrides existing tools: {names}")
            registry.update(plugin.tools)
        return registry

    def manifest(self) -> list[dict[str, object]]:
        return [
            {
                "name": plugin.name,
                "tools": sorted(plugin.tools),
                "metadata": dict(plugin.metadata),
            }
            for plugin in self._plugins
        ]


def builtin_tool_plugin(tools: Mapping[str, ToolFunction]) -> ToolPlugin:
    return ToolPlugin(
        name="builtin",
        tools=dict(tools),
        metadata={"source": "runtime.tool_registry"},
    )


__all__ = ["PluginManager", "ToolPlugin", "builtin_tool_plugin"]
