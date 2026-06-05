"""Legacy executable adapter for the canonical ANUBIS CLI.

The production CLI entrypoint lives in :mod:`anubis.cli.main`.  This file is
kept only so older invocations such as ``python anubis-cli/main.py`` continue
to work while the repository converges on one CLI runtime.
"""
from __future__ import annotations

from anubis.cli.main import main


if __name__ == "__main__":
    main()
