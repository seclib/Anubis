from __future__ import annotations

import os
import sys


def load_unified_module(relative_path: str, module_name: str):
    """Load legacy CLI modules from the Phase 1 ``cli/`` tree.

    This avoids ``importlib`` and ``pathlib`` because this repository currently
    has a root-level ``types.py`` compatibility module that can shadow the
    Python standard library during root-level imports.
    """
    root = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(root, "cli", *relative_path.split("/"))
    if not os.path.exists(target):
        raise ImportError(f"cannot load unified CLI module: {target}")

    module = type(sys)(module_name)
    module.__file__ = target
    module.__package__ = ""
    sys.modules[module_name] = module

    original_path = list(sys.path)
    root_abs = os.path.abspath(root)
    sys.path = [
        path
        for path in sys.path
        if path not in {"", root_abs}
        and os.path.abspath(path or os.getcwd()) != root_abs
    ]
    try:
        with open(target, "r", encoding="utf-8") as handle:
            code = compile(handle.read(), target, "exec")
        exec(code, module.__dict__)
    finally:
        sys.path = original_path
    return module


def get_attr(relative_path: str, module_name: str, attr: str):
    return getattr(load_unified_module(relative_path, module_name), attr)
