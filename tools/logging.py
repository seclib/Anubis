from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from anubis.types import ToolResult


class ToolCallLogger:
    def __init__(self, log_path: Path | str = Path("anubis/logs/tool_calls.jsonl")) -> None:
        self.log_path = Path(log_path)

    def log(self, result: ToolResult) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "result": result,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


__all__ = ["ToolCallLogger"]
