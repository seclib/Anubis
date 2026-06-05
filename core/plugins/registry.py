"""Deterministic plugin registry for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, replace

from core.plugins.plugin_interface import BasePlugin, PluginManifest, PluginStatus


@dataclass(frozen=True, slots=True)
class PluginRecord:
    manifest: PluginManifest
    status: PluginStatus = PluginStatus.REGISTERED
    last_error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.to_dict(),
            "status": self.status,
            "last_error": self.last_error,
        }


class PluginRegistry:
    """Registry of explicitly provided plugin instances."""

    def __init__(self) -> None:
        self._plugins: dict[str, BasePlugin] = {}
        self._records: dict[str, PluginRecord] = {}

    def register(self, plugin: BasePlugin) -> PluginRecord:
        manifest = plugin.manifest
        if manifest.plugin_id in self._plugins:
            raise ValueError(f"plugin already registered: {manifest.plugin_id}")
        self._plugins[manifest.plugin_id] = plugin
        record = PluginRecord(manifest=manifest, status=PluginStatus.REGISTERED)
        self._records[manifest.plugin_id] = record
        return record

    def get(self, plugin_id: str) -> BasePlugin:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise LookupError(f"plugin is not registered: {plugin_id}") from exc

    def record(self, plugin_id: str) -> PluginRecord:
        try:
            return self._records[plugin_id]
        except KeyError as exc:
            raise LookupError(f"plugin is not registered: {plugin_id}") from exc

    def update(
        self,
        plugin_id: str,
        status: PluginStatus,
        *,
        error: str | None = None,
    ) -> PluginRecord:
        record = replace(self.record(plugin_id), status=status, last_error=error)
        self._records[plugin_id] = record
        return record

    def records(self) -> tuple[PluginRecord, ...]:
        return tuple(self._records[plugin_id] for plugin_id in sorted(self._records))


__all__ = ["PluginRecord", "PluginRegistry"]
