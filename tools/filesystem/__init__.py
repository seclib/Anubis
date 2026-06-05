"""Filesystem tool compatibility exports."""

from __future__ import annotations

from typing import Any

from tools.sandbox import relative_to_workspace, resolve_workspace_path


def read_file(path: str) -> dict[str, Any]:
    target = resolve_workspace_path(path)
    if not target.is_file():
        raise FileNotFoundError(relative_to_workspace(target))
    return {
        "path": relative_to_workspace(target),
        "content": target.read_text(encoding="utf-8"),
    }


def write_file(path: str, content: str) -> dict[str, Any]:
    target = resolve_workspace_path(path, must_exist=False)
    if target.exists() and target.is_dir():
        raise IsADirectoryError(relative_to_workspace(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(content), encoding="utf-8")
    return {
        "path": relative_to_workspace(target),
        "bytes": len(str(content).encode("utf-8")),
    }


def list_files(path: str = ".") -> list[str]:
    target = resolve_workspace_path(path)
    if target.is_file():
        return [relative_to_workspace(target)]
    if not target.is_dir():
        raise NotADirectoryError(relative_to_workspace(target))
    return [
        relative_to_workspace(item)
        for item in sorted(target.iterdir(), key=lambda child: child.name.lower())
    ]


def __getattr__(name: str):
    if name in {"ReadFileTool", "WriteFileTool", "filesystem_tools", "resolve_path"}:
        module = __import__("tools.filesystem.tools", fromlist=[name])
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(name)


__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "filesystem_tools",
    "list_files",
    "read_file",
    "resolve_path",
    "write_file",
]
