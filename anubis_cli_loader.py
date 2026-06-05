from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def load_unified_module(relative_path: str, module_name: str) -> ModuleType:
    root = Path(__file__).resolve().parent / "anubis-cli"
    target = root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load unified CLI module: {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def get_attr(relative_path: str, module_name: str, attr: str) -> Any:
    return getattr(load_unified_module(relative_path, module_name), attr)
