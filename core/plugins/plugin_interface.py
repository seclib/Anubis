"""Safe plugin interface contracts for ANUBIS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


def _freeze_strings(values: frozenset[str] | set[str] | list[str] | tuple[str, ...]) -> frozenset[str]:
    return frozenset(sorted(str(item).strip() for item in values if str(item).strip()))


class PluginType(StrEnum):
    TOOL = "tool"
    SENSOR = "sensor"
    ANALYZER = "analyzer"
    KNOWLEDGE = "knowledge"


class PluginStatus(StrEnum):
    LOADED = "loaded"
    REGISTERED = "registered"
    STARTED = "started"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True, order=True)
class PluginVersion:
    major: int
    minor: int = 0
    patch: int = 0

    @classmethod
    def parse(cls, value: str) -> "PluginVersion":
        parts = value.strip().split(".")
        if not 1 <= len(parts) <= 3:
            raise ValueError(f"invalid plugin version: {value}")
        parsed = [int(part) for part in parts]
        while len(parsed) < 3:
            parsed.append(0)
        if any(part < 0 for part in parsed):
            raise ValueError(f"invalid plugin version: {value}")
        return cls(*parsed)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    plugin_type: PluginType
    entrypoint: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        plugin_id = self.plugin_id.strip()
        name = self.name.strip()
        entrypoint = self.entrypoint.strip()
        if not plugin_id:
            raise ValueError("plugin_id cannot be empty")
        if not name:
            raise ValueError("plugin name cannot be empty")
        if not entrypoint:
            raise ValueError("plugin entrypoint cannot be empty")
        if any(token in entrypoint for token in ("..", "/", "\\", ":", ";")):
            raise ValueError("plugin entrypoint must be a symbolic identifier, not a path")
        PluginVersion.parse(self.version)
        object.__setattr__(self, "plugin_id", plugin_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "entrypoint", entrypoint)
        object.__setattr__(self, "capabilities", _freeze_strings(self.capabilities))
        object.__setattr__(self, "permissions", _freeze_strings(self.permissions))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "plugin_type": self.plugin_type,
            "entrypoint": self.entrypoint,
            "capabilities": sorted(self.capabilities),
            "permissions": sorted(self.permissions),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class PluginRequest:
    plugin_id: str
    action: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    trace_id: str = "trace_plugin"

    def __post_init__(self) -> None:
        plugin_id = self.plugin_id.strip()
        action = self.action.strip()
        if not plugin_id:
            raise ValueError("plugin_id cannot be empty")
        if not action:
            raise ValueError("plugin action cannot be empty")
        object.__setattr__(self, "plugin_id", plugin_id)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))
        object.__setattr__(self, "trace_id", self.trace_id.strip() or "trace_plugin")


@dataclass(frozen=True, slots=True)
class PluginResult:
    ok: bool
    plugin_id: str
    output: Mapping[str, Any] = field(default_factory=dict)
    error: Mapping[str, Any] | None = None
    trace: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output", _freeze_mapping(self.output))
        if self.error is not None:
            object.__setattr__(self, "error", _freeze_mapping(self.error))
        object.__setattr__(self, "trace", tuple(self.trace))

    def to_dict(self) -> dict[str, Any]:
        data = {
            "ok": self.ok,
            "plugin_id": self.plugin_id,
            "output": dict(self.output),
            "trace": list(self.trace),
        }
        if self.error is not None:
            data["error"] = dict(self.error)
        return data


class BasePlugin(ABC):
    """Stateless plugin base. Plugins receive data only; no system handles."""

    manifest: PluginManifest

    @abstractmethod
    def execute(self, request: PluginRequest) -> Mapping[str, Any]:
        """Return a structured dictionary. Direct system access is forbidden."""


Plugin = BasePlugin


__all__ = [
    "BasePlugin",
    "Plugin",
    "PluginManifest",
    "PluginRequest",
    "PluginResult",
    "PluginStatus",
    "PluginType",
    "PluginVersion",
]
