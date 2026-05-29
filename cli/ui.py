from __future__ import annotations

import logging

from rich.console import Console

from config import STATE_DIR

VERSION = "6.0.0"
CLAUDE_ORANGE = "#d97757"
MUTED_TEXT = "#9a9a9a"

console = Console()
logger = logging.getLogger("anubis.cli")


def configure_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if logger.handlers:
        return
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.FileHandler(STATE_DIR / "cli.log", encoding="utf-8")],
    )

