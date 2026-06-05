"""Canonical Phase 1 executable adapter for the ANUBIS CLI.

Phase 1 keeps behavior on the known-good terminal agent while unifying public
entrypoints behind ``cli.main:main`` and ``anubis_cli.py``.
"""
from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> None:
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "agent.py")
    args = sys.argv[1:] if argv is None else list(argv)
    os.execv(sys.executable, [sys.executable, target, *args])


if __name__ == "__main__":
    main()
