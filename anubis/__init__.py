"""Compatibility namespace for the existing ANUBIS flat package layout.

The repository still stores most Python packages at the project root.  This
adapter lets legacy ``anubis.*`` imports resolve without moving modules during
the migration to the canonical architecture.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent
__path__ = [str(_ROOT)]


def _alias(namespace: str, target: str) -> None:
    try:
        module = importlib.import_module(target)
    except ModuleNotFoundError:
        return
    sys.modules.setdefault(f"{__name__}.{namespace}", module)


_alias("agents", "agent")


__all__: list[str] = []
