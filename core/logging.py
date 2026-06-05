from __future__ import annotations

import logging

from config import LOG_FORMAT, LOG_LEVEL


def configure_logging() -> None:
    """Configure process logging for app-level startup paths."""
    logging.basicConfig(
        level=getattr(logging, str(LOG_LEVEL).upper(), logging.INFO),
        format=LOG_FORMAT,
    )


__all__ = ["configure_logging"]
