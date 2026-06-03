"""Executor Agent error types."""

from __future__ import annotations


class ExecutorAgentError(Exception):
    """Base error for executor worker failures."""


class InvalidExecutionStepError(ExecutorAgentError):
    """Raised when an assigned execution step is malformed."""


class ToolNotAllowedError(ExecutorAgentError):
    """Raised when a step requests a tool outside the executor allowlist."""


__all__ = [
    "ExecutorAgentError",
    "InvalidExecutionStepError",
    "ToolNotAllowedError",
]
