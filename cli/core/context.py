from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.config import CliConfig, config


@dataclass
class CliContext:
    config: CliConfig = config
    state: dict[str, Any] = field(default_factory=dict)
    should_continue: bool = True

    def get_namespace(self, name: str) -> dict[str, Any]:
        value = self.state.setdefault(name, {})
        if not isinstance(value, dict):
            self.state[name] = {}
        return self.state[name]
