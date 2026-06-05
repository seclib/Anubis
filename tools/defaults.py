from __future__ import annotations

from pathlib import Path

from anubis.tools.engine import ToolExecutionEngine
from anubis.tools.filesystem import filesystem_tools
from anubis.tools.logging import ToolCallLogger
from anubis.tools.registry import ToolRegistry


def create_default_tool_engine(log_path: Path | str = Path("anubis/logs/tool_calls.jsonl")) -> ToolExecutionEngine:
    registry = ToolRegistry(filesystem_tools())
    return ToolExecutionEngine(registry=registry, logger=ToolCallLogger(log_path))


__all__ = ["create_default_tool_engine"]
