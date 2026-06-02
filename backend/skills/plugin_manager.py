from __future__ import annotations
from dataclasses import dataclass, field, replace
from pathlib import Path
import json
import os
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
        "name": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$",
            "description": "Stable plugin identifier.",
        },
        "display_name": {"type": "string"},
        "version": {"type": "string"},
        "description": {"type": "string"},
        "enabled": {"type": "boolean", "default": True},
        "triggers": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
            "description": "Literal trigger phrases or regex strings wrapped in /slashes/.",
        },
        "skills": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
            "description": "Markdown files or directories under /skills/ to load as skill context.",
        },
        "activation_events": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional VS Code-style activation labels.",
        },
        "memory": {
            "type": "object",
            "additionalProperties": False,
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
        return {
            "plugin": self.plugin,
            "trigger": self.trigger,
            "kind": self.kind,
            "score": self.score,
        }


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


class PluginError(ValueError):
    pass


PluginFormatError = PluginError


class TriggerRouter:
    def __init__(self) -> None:
        self.routes: dict[str, tuple[tuple[str, str, re.Pattern[str]], ...]] = {}

    def clear(self) -> None:
        self.routes.clear()

    def register(self, plugin: PluginSpec) -> None:
        self.routes[plugin.name] = tuple(self._compile(item) for item in plugin.triggers if item.strip())

    def unregister(self, name: str) -> None:
        self.routes.pop(name, None)

    def match(self, query: str) -> tuple[str, ...]:
        return tuple(match.plugin for match in self.route(query))

    def route(self, query: str) -> tuple[RouteMatch, ...]:
        matches: list[RouteMatch] = []
        for name, patterns in self.routes.items():
            best: RouteMatch | None = None
            for raw, kind, pattern in patterns:
                found = pattern.search(query)
                if not found:
                    continue
                score = self._score(query, found, kind)
                candidate = RouteMatch(name, raw, kind, score)
                if best is None or candidate.score > best.score:
                    best = candidate
            if best is not None:
                matches.append(best)
        matches.sort(key=lambda item: (item.score, item.plugin), reverse=True)
        return tuple(matches)

    def _compile(self, trigger: str) -> tuple[str, str, re.Pattern[str]]:
        trigger = trigger.strip()
        if trigger.startswith("/") and trigger.endswith("/") and len(trigger) > 2:
            return trigger, "regex", re.compile(trigger[1:-1], re.IGNORECASE)
        words = re.findall(r"[a-zA-Z0-9_+#.-]+", trigger)
        pattern = r".*".join(map(re.escape, words)) if words else re.escape(trigger)
        return trigger, "phrase", re.compile(pattern, re.IGNORECASE)

    def _score(self, query: str, match: re.Match[str], kind: str) -> float:
        coverage = (match.end() - match.start()) / max(len(query), 1)
        base = 0.65 if kind == "regex" else 0.75
        return round(min(1.0, base + coverage), 6)


class MemoryBinder:
    def __init__(self, vault_path: Path | None = None, qdrant_collection: str | None = None) -> None:
        self.vault_path = vault_path or Path(os.getenv("ANUBIS_VAULT_PATH", os.getenv("OBSIDIAN_VAULT_PATH", "vault")))
        self.qdrant_collection = qdrant_collection or os.getenv("QDRANT_COLLECTION", "anubis_chunks")

    def bind(self, plugin: PluginSpec) -> tuple[MemoryBinding, ...]:
        bindings: list[MemoryBinding] = []
        for namespace in plugin.obsidian:
            source = _inside(self.vault_path, Path(namespace))
            bindings.append(MemoryBinding("obsidian", namespace, source.as_posix(), {"vault": self.vault_path.as_posix()}))
        for namespace in plugin.qdrant:
            meta = {"collection": self.qdrant_collection, "filter": {"namespace": namespace}}
            bindings.append(MemoryBinding("qdrant", namespace, self.qdrant_collection, meta))
        return tuple(bindings)


class PluginLoader:
    def __init__(self, root: Path | str = Path("skills")) -> None:
        self.root = Path(root).resolve()

    def discover(self) -> tuple[Path, ...]:
        if not self.root.exists():
            return ()
        manifests = {*self.root.glob("*.plugin.json"), *self.root.glob("*/plugin.json")}
        return tuple(sorted(manifests))

    def parse(self, path: Path) -> PluginSpec:
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.validate_manifest(raw, path)
        memory = raw.get("memory", {})
        name = str(raw.get("name") or path.name.removesuffix(".plugin.json")).strip()
        triggers = _strings(raw.get("triggers", ()))
        return PluginSpec(
            name=name,
            path=path,
            triggers=triggers,
            skills=_strings(raw.get("skills", (name,))),
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
        location = str(path or "plugin manifest")
        if not isinstance(raw, dict):
            raise PluginError(f"{location} must contain a JSON object")
        missing = {"name", "triggers", "skills"} - set(raw)
        if missing:
            raise PluginError(f"{location} missing required keys: {', '.join(sorted(missing))}")
        name = str(raw.get("name") or "")
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$", name):
            raise PluginError(f"{location} name must be a safe plugin id")
        if not _strings(raw.get("triggers")):
            raise PluginError(f"{location} requires at least one trigger")
        if not _strings(raw.get("skills")):
            raise PluginError(f"{location} requires at least one skill path")
        memory = raw.get("memory", {})
        if memory is not None and not isinstance(memory, dict):
            raise PluginError(f"{location} memory must be an object")
        permissions = raw.get("permissions", {})
        if permissions is not None and not isinstance(permissions, dict):
            raise PluginError(f"{location} permissions must be an object")

    def load_skills(self, plugin: PluginSpec) -> tuple[str, ...]:
        contexts: list[str] = []
        for entry in plugin.skills:
            base = _inside(self.root, Path(entry))
            paths = sorted(base.rglob("*.md")) if base.is_dir() else [base]
            for path in paths:
                if path.suffix == ".md":
                    contexts.append(_skill_context(path.relative_to(self.root).as_posix(), path.read_text(encoding="utf-8")))
        return tuple(contexts)


class PluginRegistry:
    def __init__(self) -> None:
        self.specs: dict[str, PluginSpec] = {}
        self.active: dict[str, ActivePlugin] = {}
        self.disabled: set[str] = set()
        self.mtimes: dict[Path, float] = {}

    def set_specs(self, specs: tuple[PluginSpec, ...]) -> None:
        self.specs = {spec.name: replace(spec, enabled=False) if spec.name in self.disabled else spec for spec in specs}
        self.mtimes.update({spec.path: spec.path.stat().st_mtime for spec in specs})


class PluginManager:
    def __init__(self, root: Path | str = Path("skills"), vault_path: Path | None = None, qdrant_collection: str | None = None) -> None:
        self.loader = PluginLoader(root)
        self.router = TriggerRouter()
        self.memory = MemoryBinder(vault_path, qdrant_collection)
        self.registry = PluginRegistry()

    def discover(self) -> dict[str, PluginSpec]:
        specs = tuple(self.loader.parse(path) for path in self.loader.discover())
        self.registry.set_specs(specs)
        self._rebuild_routes()
        return self.registry.specs

    def list_plugins(self) -> list[dict[str, Any]]:
        if not self.registry.specs:
            self.discover()
        return [
            {
                **spec.manifest(),
                "active": name in self.registry.active,
                "enabled": spec.enabled and name not in self.registry.disabled,
            }
            for name, spec in sorted(self.registry.specs.items())
        ]

    def load(self, name: str) -> ActivePlugin:
        spec = self._spec(name)
        if not spec.enabled or name in self.registry.disabled:
            raise PluginError(f"plugin disabled: {name}")
        plugin = ActivePlugin(spec, self.loader.load_skills(spec), self.memory.bind(spec))
        self.registry.active[name] = plugin
        return plugin

    def unload(self, name: str) -> None:
        self.registry.active.pop(name, None)

    def enable(self, name: str) -> ActivePlugin:
        self.registry.disabled.discard(name)
        spec = replace(self._spec(name), enabled=True)
        self.registry.specs[name] = spec
        self.router.register(spec)
        return self.load(name)

    def disable(self, name: str) -> None:
        self.registry.disabled.add(name)
        self.unload(name)
        self.router.unregister(name)
        if name in self.registry.specs:
            self.registry.specs[name] = replace(self.registry.specs[name], enabled=False)

    def hot_reload(self) -> tuple[str, ...]:
        if not self.registry.specs:
            self.discover()
            return ()
        changed: list[str] = []
        for name, spec in list(self.registry.specs.items()):
            mtime = spec.path.stat().st_mtime
            if mtime == self.registry.mtimes.get(spec.path):
                continue
            self.registry.mtimes[spec.path] = mtime
            self.registry.specs[name] = self.loader.parse(spec.path)
            self.router.unregister(name)
            if name not in self.registry.disabled and self.registry.specs[name].enabled:
                self.router.register(self.registry.specs[name])
                if name in self.registry.active:
                    self.load(name)
            changed.append(name)
        return tuple(changed)

    def route(self, query: str) -> list[dict[str, Any]]:
        self.hot_reload()
        return [match.as_dict() for match in self.router.route(query)]

    def resolve(self, query: str) -> dict[str, Any]:
        self.hot_reload()
        route_matches = self.router.route(query)
        active = [
            self.registry.active[match.plugin] if match.plugin in self.registry.active else self.load(match.plugin)
            for match in route_matches
        ]
        return {
            "query": query,
            "matches": tuple(match.plugin for match in route_matches),
            "routes": [match.as_dict() for match in route_matches],
            "active_context": [plugin.context() for plugin in active],
        }

    def _spec(self, name: str) -> PluginSpec:
        if not self.registry.specs:
            self.discover()
        if name not in self.registry.specs:
            raise PluginError(f"unknown plugin: {name}")
        return self.registry.specs[name]

    def _rebuild_routes(self) -> None:
        self.router.clear()
        for spec in self.registry.specs.values():
            if spec.enabled and spec.name not in self.registry.disabled:
                self.router.register(spec)


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _inside(root: Path, candidate: Path) -> Path:
    base = root.resolve()
    resolved = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    if base != resolved and base not in resolved.parents:
        raise ValueError(f"path escapes root: {candidate}")
    return resolved


def _skill_context(path: str, markdown: str) -> str:
    body = re.sub(r"\A---\n.*?\n---\n?", "", markdown, flags=re.DOTALL)
    name = Path(path).stem
    for line in body.splitlines():
        if line.strip().startswith("#"):
            title = line.strip().lstrip("#").strip()
            name = title.split(":", 1)[1].strip() if title.lower().startswith("skill:") else title
            break
    return f"# skill: {name}\npath: {path}\n\n{body.strip()}".strip()


SkillPlugin = PluginSpec
ActiveSkillPack = ActivePlugin
TriggerRegistry = TriggerRouter
PluginRoute = RouteMatch
