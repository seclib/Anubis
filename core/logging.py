"""Central logging setup for Anubis services."""

from __future__ import annotations

import logging

from config import LOG_FORMAT, LOG_LEVEL


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, str(LOG_LEVEL).upper(), logging.INFO),
        format=LOG_FORMAT,
        force=False,
    )


__all__ = ["configure_logging"]

