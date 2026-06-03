from __future__ import annotations

import shutil
import subprocess
from typing import Any, Mapping

from backend.core.config import settings
from backend.tools.base import BaseTool, require_string
from backend.tools.filesystem import resolve_project_path


class SearchCodebaseTool(BaseTool):
    name = "search_codebase"

    def run(self, tool_input: Mapping[str, Any]) -> dict[str, Any]:
        query = require_string(tool_input, "query")
        root = resolve_project_path(str(tool_input.get("path", ".")))
        if not root.exists():
            raise FileNotFoundError(str(root))

        command = self._command(query, root)
        completed = subprocess.run(
            command,
            cwd=settings.project_root.resolve(),
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "query": query,
            "matches": completed.stdout.splitlines(),
            "stderr": completed.stderr,
            "code": completed.returncode,
        }

    def _command(self, query: str, root: object) -> list[str]:
        rg = shutil.which("rg")
        if rg:
            return [rg, "-n", "--hidden", "--glob", "!.git", "--glob", "!node_modules", "--", query, str(root)]
        return ["grep", "-rHn", "--exclude-dir=.git", "--exclude-dir=node_modules", "--", query, str(root)]


def search_codebase(query: str) -> dict[str, Any]:
    return SearchCodebaseTool().invoke({"query": query})


__all__ = ["SearchCodebaseTool", "search_codebase"]
