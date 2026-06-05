from __future__ import annotations

import logging

from core.config import config


def configure_logging() -> logging.Logger:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("anubis.cli")
    if not logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            handlers=[logging.FileHandler(config.state_dir / "anubis-cli.log", encoding="utf-8")],
        )
    return logger
