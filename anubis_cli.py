#!/usr/bin/env python3
from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> None:
    """Compatibility entrypoint for the canonical Phase 1 CLI.

    The current stable runtime is ``cli/core/agent.py``.  Use process
    delegation instead of importing it from the repository root, where
    root-level compatibility modules can shadow Python stdlib modules.
    """
    root = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(root, "cli", "core", "agent.py")
    args = sys.argv[1:] if argv is None else list(argv)
    os.execv(sys.executable, [sys.executable, target, *args])


if __name__ == "__main__":
    main()
