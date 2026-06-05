"""Plugin ecosystem facade for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.plugins.loader import PluginLoader
from core.plugins.plugin_interface import BasePlugin, PluginRequest
from core.plugins.plugin_manager import PluginManager


@dataclass(slots=True)
class PluginEcosystem:
    """OS-like extension surface with sandboxed execution only."""

    manager: PluginManager = field(default_factory=PluginManager)
    loader: PluginLoader = field(default_factory=PluginLoader)

    def inspect_manifest(self, path: str | Path) -> dict[str, Any]:
        return self.loader.load_manifest(path).to_dict()

    def install_instance(self, plugin: BasePlugin) -> dict[str, Any]:
        return self.manager.register(plugin).to_dict()

    def start(self, plugin_id: str) -> dict[str, Any]:
        return self.manager.start(plugin_id).to_dict()

    def stop(self, plugin_id: str) -> dict[str, Any]:
        return self.manager.stop(plugin_id).to_dict()

    def execute(
        self,
        *,
        plugin_id: str,
        action: str,
        payload: Mapping[str, Any] | None = None,
        trace_id: str = "trace_plugin_ecosystem",
    ) -> dict[str, Any]:
        return self.manager.execute(
            PluginRequest(
                plugin_id=plugin_id,
                action=action,
                payload=payload or {},
                trace_id=trace_id,
            )
        )

    def catalog(self) -> tuple[dict[str, Any], ...]:
        return tuple(record.to_dict() for record in self.manager.registry.records())


__all__ = ["PluginEcosystem"]
