from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import re
import time
from typing import Any


PLUGIN_MANIFEST_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://anubis.local/schemas/plugin-manifest.schema.json",
    "title": "Anubis OS Skill Plugin Manifest",
    "type": "object",
    "required": ["name", "triggers", "skills"],
    "additionalProperties": True,
    "properties": {
        "name": {"type": "string", "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$"},
        "display_name": {"type": "string"},
        "version": {"type": "string"},
        "description": {"type": "string"},
        "enabled": {"type": "boolean", "default": True},
        "triggers": {"type": "array", "items": {"type": "string"}},
        "skills": {"type": "array", "items": {"type": "string"}},
        "activation_events": {"type": "array", "items": {"type": "string"}},
        "memory": {
            "type": "object",
            "properties": {
                "obsidian": {"type": "array", "items": {"type": "string"}},
                "qdrant": {"type": "array", "items": {"type": "string"}},
            },
        },
        "permissions": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "tools": {"type": "array", "items": {"type": "string"}},
                "network": {"type": "boolean", "default": False},
                "filesystem": {"type": "string"},
            },
        },
    },
}


class PluginError(ValueError):
    pass


PluginFormatError = PluginError


@dataclass(frozen=True)
class MemoryBinding:
    kind: str
    namespace: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginSpec:
    name: str
    path: Path
    triggers: tuple[str, ...]
    skills: tuple[str, ...]
    display_name: str = ""
    version: str = "0.0.0"
    description: str = ""
    activation_events: tuple[str, ...] = ()
    permissions: dict[str, Any] = field(default_factory=dict)
    obsidian: tuple[str, ...] = ()
    qdrant: tuple[str, ...] = ()
    enabled: bool = True

    def manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "description": self.description,
            "enabled": self.enabled,
            "triggers": list(self.triggers),
            "activation_events": list(self.activation_events),
            "skills": list(self.skills),
            "memory": {"obsidian": list(self.obsidian), "qdrant": list(self.qdrant)},
            "permissions": self.permissions,
            "manifest_path": self.path.as_posix(),
        }


@dataclass(frozen=True)
class RouteMatch:
    plugin: str
    trigger: str
    kind: str
    score: float

    def as_dict(self) -> dict[str, Any]:
        return {"plugin": self.plugin, "trigger": self.trigger, "kind": self.kind, "score": self.score}


@dataclass
class ActivePlugin:
    spec: PluginSpec
    skill_context: tuple[str, ...]
    memory: tuple[MemoryBinding, ...]
    loaded_at: float = field(default_factory=time.time)

    def context(self) -> dict[str, Any]:
        return {
            "plugin": self.spec.name,
            "manifest": self.spec.manifest(),
            "skills": self.skill_context,
            "memory": [binding.__dict__ for binding in self.memory],
            "loaded_at": self.loaded_at,
        }


class TriggerRouter:
    def __init__(self) -> None:
        self.routes: dict[str, tuple[tuple[str, str, re.Pattern[str]], ...]] = {}

    def clear(self) -> None:
        self.routes.clear()

    def register(self, plugin: PluginSpec) -> None:
        self.routes[plugin.name] = tuple(self._compile(trigger) for trigger in plugin.triggers if trigger.strip())

    def unregister(self, name: str) -> None:
        self.routes.pop(name, None)

    def match(self, query: str) -> tuple[str, ...]:
        return tuple(match.plugin for match in self.route(query))

    def route(self, query: str) -> tuple[RouteMatch, ...]:
        matches: list[RouteMatch] = []
        for name, routes in self.routes.items():
            best: RouteMatch | None = None
            for raw, kind, pattern in routes:
                found = pattern.search(query)
                if found is None:
                    continue
                coverage = (found.end() - found.start()) / max(len(query), 1)
                score = round(min(1.0, (0.65 if kind == "regex" else 0.75) + coverage), 6)
                candidate = RouteMatch(name, raw, kind, score)
                if best is None or candidate.score > best.score:
                    best = candidate
            if best is not None:
                matches.append(best)
        return tuple(sorted(matches, key=lambda item: (item.score, item.plugin), reverse=True))

    def _compile(self, trigger: str) -> tuple[str, str, re.Pattern[str]]:
        trigger = trigger.strip()
        if trigger.startswith("/") and trigger.endswith("/") and len(trigger) > 2:
            return trigger, "regex", re.compile(trigger[1:-1], re.IGNORECASE)
        words = re.findall(r"[a-zA-Z0-9_+#.-]+", trigger)
        return trigger, "phrase", re.compile(r".*".join(map(re.escape, words)) or re.escape(trigger), re.IGNORECASE)


class MemoryBinder:
    def __init__(self, vault_path: Path | None = None, qdrant_collection: str | None = None) -> None:
        vault = os.getenv("ANUBIS_VAULT_PATH", os.getenv("OBSIDIAN_VAULT_PATH", "vault"))
        self.vault_path = Path(vault_path or vault)
        self.qdrant_collection = qdrant_collection or os.getenv("QDRANT_COLLECTION", "anubis_chunks")

    def bind(self, plugin: PluginSpec) -> tuple[MemoryBinding, ...]:
        bindings: list[MemoryBinding] = []
        for namespace in plugin.obsidian:
            source = _inside(self.vault_path, Path(namespace))
            bindings.append(MemoryBinding("obsidian", namespace, source.as_posix(), {"vault": self.vault_path.as_posix()}))
        for namespace in plugin.qdrant:
            metadata = {"collection": self.qdrant_collection, "filter": {"namespace": namespace}}
            bindings.append(MemoryBinding("qdrant", namespace, self.qdrant_collection, metadata))
        return tuple(bindings)


class PluginLoader:
    def __init__(self, root: Path | str = Path("skills")) -> None:
        self.root = Path(root).resolve()

    def discover(self) -> tuple[Path, ...]:
        if not self.root.exists():
            return ()
        return tuple(sorted({*self.root.glob("*.plugin.json"), *self.root.glob("*/plugin.json")}))

    def parse(self, path: Path) -> PluginSpec:
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.validate_manifest(raw, path)
        memory = raw.get("memory") or {}
        name = str(raw["name"]).strip()
        return PluginSpec(
            name=name,
            path=path,
            triggers=_strings(raw["triggers"]),
            skills=_strings(raw["skills"]),
            display_name=str(raw.get("display_name") or raw.get("displayName") or name),
            version=str(raw.get("version") or "0.0.0"),
            description=str(raw.get("description") or ""),
            activation_events=_strings(raw.get("activation_events", raw.get("activationEvents", ()))),
            permissions=dict(raw.get("permissions") or {}),
            obsidian=_strings(memory.get("obsidian", ())),
            qdrant=_strings(memory.get("qdrant", ())),
            enabled=bool(raw.get("enabled", True)),
        )

    def validate_manifest(self, raw: Any, path: Path | None = None) -> None:
        label = str(path or "plugin manifest")
        if not isinstance(raw, dict):
            raise PluginError(f"{label} must contain a JSON object")
        missing = {"name", "triggers", "skills"} - set(raw)
        if missing:
            raise PluginError(f"{label} missing required keys: {', '.join(sorted(missing))}")
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$", str(raw["name"])):
            raise PluginError(f"{label} name must be a safe plugin id")
        if not _strings(raw["triggers"]) or not _strings(raw["skills"]):
            raise PluginError(f"{label} requires at least one trigger and one skill")
        if raw.get("memory") is not None and not isinstance(raw["memory"], dict):
            raise PluginError(f"{label} memory must be an object")
        if raw.get("permissions") is not None and not isinstance(raw["permissions"], dict):
            raise PluginError(f"{label} permissions must be an object")

    def load_skills(self, plugin: PluginSpec) -> tuple[str, ...]:
        contexts: list[str] = []
        for entry in plugin.skills:
            base = _inside(self.root, Path(entry))
            for path in sorted(base.rglob("*.md")) if base.is_dir() else [base]:
                if path.suffix == ".md":
                    contexts.append(_skill_context(path.relative_to(self.root).as_posix(), path.read_text(encoding="utf-8")))
        return tuple(contexts)


class PluginManager:
    def __init__(self, root: Path | str = Path("skills"), vault_path: Path | None = None, qdrant_collection: str | None = None) -> None:
        self.loader = PluginLoader(root)
        self.router = TriggerRouter()
        self.memory = MemoryBinder(vault_path, qdrant_collection)
        self.specs: dict[str, PluginSpec] = {}
        self.active_plugins: dict[str, ActivePlugin] = {}
        self.disabled: set[str] = set()
        self.mtimes: dict[Path, float] = {}

    def discover(self) -> dict[str, PluginSpec]:
        self.specs = {}
        self.mtimes = {}
        for spec in (self.loader.parse(path) for path in self.loader.discover()):
            self.specs[spec.name] = replace(spec, enabled=False) if spec.name in self.disabled else spec
            self.mtimes[spec.path] = spec.path.stat().st_mtime
        self._rebuild_routes()
        return self.specs

    def list_plugins(self) -> list[dict[str, Any]]:
        if not self.specs:
            self.discover()
        return [
            {**spec.manifest(), "active": name in self.active_plugins, "enabled": self.enabled(name)}
            for name, spec in sorted(self.specs.items())
        ]

    def load(self, name: str) -> ActivePlugin:
        spec = self._spec(name)
        if not self.enabled(name):
            raise PluginError(f"plugin disabled: {name}")
        plugin = ActivePlugin(spec, self.loader.load_skills(spec), self.memory.bind(spec))
        self.active_plugins[name] = plugin
        return plugin

    def unload(self, name: str) -> None:
        self.active_plugins.pop(name, None)

    def enable(self, name: str) -> ActivePlugin:
        self.disabled.discard(name)
        self.specs[name] = replace(self._spec(name), enabled=True)
        self.router.register(self.specs[name])
        return self.load(name)

    def disable(self, name: str) -> None:
        self.disabled.add(name)
        self.unload(name)
        self.router.unregister(name)
        if name in self.specs:
            self.specs[name] = replace(self.specs[name], enabled=False)

    def enabled(self, name: str) -> bool:
        spec = self._spec(name)
        return spec.enabled and name not in self.disabled

    def active(self, name: str) -> bool:
        return name in self.active_plugins

    def bindings(self, name: str) -> tuple[MemoryBinding, ...]:
        plugin = self.active_plugins.get(name)
        if plugin is None:
            plugin = self.load(name)
        return plugin.memory

    def hot_reload(self) -> tuple[str, ...]:
        if not self.specs:
            self.discover()
            return ()
        current = {spec.name: spec for spec in (self.loader.parse(path) for path in self.loader.discover())}
        changed: list[str] = []
        for name in tuple(self.specs):
            if name not in current:
                self.disable(name)
                self.specs.pop(name, None)
                changed.append(name)
        for name, spec in current.items():
            mtime = spec.path.stat().st_mtime
            if name in self.specs and self.mtimes.get(spec.path) == mtime:
                continue
            self.specs[name] = replace(spec, enabled=False) if name in self.disabled else spec
            self.mtimes[spec.path] = mtime
            self.router.unregister(name)
            if self.enabled(name):
                self.router.register(self.specs[name])
                if name in self.active_plugins:
                    self.load(name)
            changed.append(name)
        self.mtimes = {path: mtime for path, mtime in self.mtimes.items() if path.exists()}
        return tuple(changed)

    reload = hot_reload

    def route(self, query: str) -> list[dict[str, Any]]:
        self.hot_reload()
        return [match.as_dict() for match in self.router.route(query)]

    def resolve(self, query: str) -> dict[str, Any]:
        self.hot_reload()
        matches = self.router.route(query)
        active = [self.active_plugins.get(match.plugin) or self.load(match.plugin) for match in matches]
        return {
            "query": query,
            "matches": tuple(match.plugin for match in matches),
            "routes": [match.as_dict() for match in matches],
            "active_context": [plugin.context() for plugin in active],
        }

    def registry_snapshot(self) -> dict[str, Any]:
        return {
            "plugins": self.list_plugins(),
            "routes": {name: [raw for raw, _kind, _pattern in routes] for name, routes in sorted(self.router.routes.items())},
            "active": sorted(self.active_plugins),
            "disabled": sorted(self.disabled),
        }

    def _spec(self, name: str) -> PluginSpec:
        if not self.specs:
            self.discover()
        if name not in self.specs:
            raise PluginError(f"unknown plugin: {name}")
        return self.specs[name]

    def _rebuild_routes(self) -> None:
        self.router.clear()
        for spec in self.specs.values():
            if spec.enabled and spec.name not in self.disabled:
                self.router.register(spec)


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _inside(root: Path, candidate: Path) -> Path:
    base = root.resolve()
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    if base != resolved and base not in resolved.parents:
        raise ValueError(f"path escapes root: {candidate}")
    return resolved


def _skill_context(path: str, markdown: str) -> str:
    body = re.sub(r"\A---\n.*?\n---\n?", "", markdown, flags=re.DOTALL).strip()
    title = Path(path).stem
    for line in body.splitlines():
        if line.strip().startswith("#"):
            title = line.strip().lstrip("#").strip()
            title = title.split(":", 1)[1].strip() if title.lower().startswith("skill:") else title
            break
    return f"# skill: {title}\npath: {path}\n\n{body}".strip()


SkillPlugin = PluginSpec
ActiveSkillPack = ActivePlugin
TriggerRegistry = TriggerRouter
PluginRoute = RouteMatch
