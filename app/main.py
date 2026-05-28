"""Container entrypoint that delegates to the existing CLI."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_SOURCE = Path(__file__).resolve().parent.parent
if str(PROJECT_SOURCE) not in sys.path:
    sys.path.insert(0, str(PROJECT_SOURCE))

from main import main as legacy_main


def main() -> None:
    legacy_main()


if __name__ == "__main__":
    main()
