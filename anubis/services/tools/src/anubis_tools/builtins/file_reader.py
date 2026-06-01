from __future__ import annotations

from pathlib import Path
from typing import Any
import asyncio

from pydantic import BaseModel, Field

from anubis_tools.core.schemas import ToolDefinition


class FileReaderInput(BaseModel):
    relative_path: str = Field(min_length=1, max_length=500)
    max_bytes: int = Field(default=12000, ge=1, le=200000)


class FileReaderTool:
    def __init__(self, workspace_root: str) -> None:
        self._root = Path(workspace_root).resolve()
        self.definition = ToolDefinition(
            name="file.read",
            description="Reads a text file inside the configured workspace root.",
            input_schema=FileReaderInput.model_json_schema(),
            output_schema={"type": "object", "properties": {"content": {"type": "string"}}},
        )

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        request = FileReaderInput.model_validate(arguments)
        path = (self._root / request.relative_path).resolve()
        if self._root not in path.parents and path != self._root:
            raise ValueError("Path escapes workspace")
        if not path.is_file():
            raise ValueError("File does not exist")
        raw = await asyncio.to_thread(path.read_bytes)
        content = raw[: request.max_bytes].decode("utf-8", errors="replace")
        return {"content": content, "display_path": request.relative_path}
