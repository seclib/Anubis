from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.base import ModuleOption


class ModuleLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConsoleModule:
    name: str
    domain: str
    description: str
    options: tuple[ModuleOption, ...]
    instance: Any
    aliases: tuple[str, ...] = ()

    @classmethod
    def from_instance(cls, instance: Any) -> ConsoleModule:
        info = instance.info()
        options = tuple(instance.options())
        return cls(
            name=str(info.get("name") or getattr(instance, "name")),
            domain=str(info.get("domain") or getattr(instance, "domain")),
            description=str(info.get("description") or ""),
            options=options,
            instance=instance,
            aliases=tuple(getattr(instance, "aliases", ())),
        )

    def defaults(self) -> dict[str, str]:
        return {option.name: option.default for option in self.options if option.default is not None}

    def validate(self, values: dict[str, str]) -> list[str]:
        missing = []
        for option in self.options:
            if option.required and not values.get(option.name):
                missing.append(option.name)
        return missing

    def run(self, values: dict[str, str]) -> dict[str, Any]:
        return self.instance.run(values)


class ModuleRegistry:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path("modules")
        self._modules: dict[str, ConsoleModule] = {}
        self._aliases: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self._modules.clear()
        self._aliases.clear()
        for package_dir in sorted(self.root.iterdir() if self.root.exists() else []):
            if not package_dir.is_dir() or package_dir.name.startswith("__"):
                continue
            module_file = package_dir / "console_module.py"
            if not module_file.exists():
                continue
            self.load_module(f"modules.{package_dir.name}.console_module")

    def load_module(self, import_path: str) -> ConsoleModule:
        try:
            loaded = importlib.import_module(import_path)
            module_cls = getattr(loaded, "Module")
            instance = module_cls()
            module = ConsoleModule.from_instance(instance)
        except Exception as exc:
            raise ModuleLoadError(f"failed to load {import_path}: {exc}") from exc
        self.register(module)
        return module

    def register(self, module: ConsoleModule) -> None:
        key = self._normalize(module.name)
        self._modules[key] = module
        for alias in (module.name, module.domain, *module.aliases):
            self._aliases[self._normalize(alias)] = key

    def get(self, name: str) -> ConsoleModule | None:
        key = self._aliases.get(self._normalize(name))
        return self._modules.get(key) if key else None

    def list(self) -> list[ConsoleModule]:
        return [self._modules[key] for key in sorted(self._modules)]

    def _normalize(self, value: str) -> str:
        return value.strip().lower().replace(" ", "_")
