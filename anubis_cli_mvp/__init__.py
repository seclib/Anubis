"""Backward-compatible alias for the renamed :mod:`cli_mvp` package."""

from cli_mvp import *  # noqa: F401,F403
from cli_mvp import __path__ as __path__  # re-export submodule search path
