from __future__ import annotations

from pathlib import Path


class FilesystemTool:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or Path.cwd()).resolve()

    def execute(self, input: dict) -> dict:
        action = str(input.get("action", "")).strip().lower()
        if action == "read_file":
            return self._read_file(input)
        if action == "write_file":
            return self._write_file(input)
        if action == "list_directory":
            return self._list_directory(input)
        return {"ok": False, "error": f"unknown filesystem action: {action}"}

    def _read_file(self, input: dict) -> dict:
        path = self._resolve(str(input.get("path", "")))
        if not path.is_file():
            return {"ok": False, "error": f"file not found: {self._relative(path)}"}
        return {
            "ok": True,
            "action": "read_file",
            "path": self._relative(path),
            "content": path.read_text(encoding="utf-8"),
        }

    def _write_file(self, input: dict) -> dict:
        path = self._resolve(str(input.get("path", "")))
        content = str(input.get("content", ""))
        if path.exists() and path.is_dir():
            return {"ok": False, "error": f"path is a directory: {self._relative(path)}"}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "ok": True,
            "action": "write_file",
            "path": self._relative(path),
            "bytes": len(content.encode("utf-8")),
        }

    def _list_directory(self, input: dict) -> dict:
        path = self._resolve(str(input.get("path", ".")))
        if not path.is_dir():
            return {"ok": False, "error": f"directory not found: {self._relative(path)}"}
        entries = [
            {
                "name": child.name,
                "path": self._relative(child),
                "type": "directory" if child.is_dir() else "file",
            }
            for child in sorted(path.iterdir(), key=lambda item: item.name.lower())
        ]
        return {
            "ok": True,
            "action": "list_directory",
            "path": self._relative(path),
            "entries": entries,
        }

    def _resolve(self, value: str) -> Path:
        if not value:
            value = "."
        path = Path(value)
        candidate = path.resolve() if path.is_absolute() else (self.root / path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError(f"path escapes project root: {value}")
        return candidate

    def _relative(self, path: Path) -> str:
        return str(path.relative_to(self.root))


__all__ = ["FilesystemTool"]
