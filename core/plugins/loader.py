"""Safe manifest loader for ANUBIS plugins.

The loader reads declarative JSON manifests only. It does not import modules,
evaluate source, or instantiate plugin code.
"""

from __future__ import annotations

from json import loads
from pathlib import Path
from typing import Any, Mapping

from core.plugins.plugin_interface import PluginManifest, PluginType


class PluginLoadError(ValueError):
    """Raised when a plugin manifest cannot be safely loaded."""


class PluginLoader:
    """Loads plugin manifests from trusted declarative files."""

    def load_manifest(self, path: str | Path) -> PluginManifest:
        manifest_path = Path(path)
        if manifest_path.suffix != ".json":
            raise PluginLoadError("plugin manifest must be a JSON file")
        try:
            raw = loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise PluginLoadError(f"failed to read plugin manifest: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise PluginLoadError("plugin manifest must contain a JSON object")
        return self.from_dict(raw)

    def from_dict(self, data: Mapping[str, Any]) -> PluginManifest:
        try:
            plugin_type = PluginType(str(data["plugin_type"]))
            return PluginManifest(
                plugin_id=str(data["plugin_id"]),
                name=str(data["name"]),
                version=str(data["version"]),
                plugin_type=plugin_type,
                entrypoint=str(data["entrypoint"]),
                capabilities=frozenset(str(item) for item in data.get("capabilities", ())),
                permissions=frozenset(str(item) for item in data.get("permissions", ())),
                metadata=dict(data.get("metadata", {})),
            )
        except KeyError as exc:
            raise PluginLoadError(f"missing manifest field: {exc.args[0]}") from exc
        except Exception as exc:
            raise PluginLoadError(f"invalid plugin manifest: {exc}") from exc


__all__ = ["PluginLoadError", "PluginLoader"]
