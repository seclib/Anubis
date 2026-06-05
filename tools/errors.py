from __future__ import annotations


class ToolError(RuntimeError):
    """Base error for retry-safe tool failures."""


class ToolNotFoundError(ToolError):
    """Raised when a requested tool is not registered."""


class ToolValidationError(ToolError):
    """Raised when tool input does not match the declared schema."""


class ToolExecutionError(ToolError):
    """Raised when a tool fails during execution."""


__all__ = [
    "ToolError",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolValidationError",
]
