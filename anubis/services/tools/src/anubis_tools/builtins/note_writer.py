from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from anubis_tools.core.schemas import ToolDefinition


class NoteWriterInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=20000)


class NoteWriterTool:
    def __init__(self, workspace_root: str) -> None:
        self._notes_dir = Path(workspace_root).resolve() / "notes"
        self.definition = ToolDefinition(
            name="note.write",
            description="Writes a markdown note to the workspace notes directory.",
            input_schema=NoteWriterInput.model_json_schema(),
            output_schema={"type": "object", "properties": {"note_id": {"type": "string"}}},
        )

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        request = NoteWriterInput.model_validate(arguments)
        self._notes_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", request.title.lower()).strip("-") or "note"
        note_id = f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{slug}.md"
        path = self._notes_dir / note_id
        await asyncio.to_thread(path.write_text, f"# {request.title}\n\n{request.content}\n", encoding="utf-8")
        return {"note_id": note_id, "display_path": f"notes/{note_id}"}
