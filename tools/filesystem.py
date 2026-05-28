from pathlib import Path
from typing import List

from tools.sandbox import relative_to_workspace, resolve_workspace_path


def read_file(path: str) -> str:
    safe_path = resolve_workspace_path(path, must_exist=True)
    if not safe_path.is_file():
        raise IsADirectoryError(f"Not a file: {relative_to_workspace(safe_path)}")
    return safe_path.read_text()


def write_file(path: str, content: str) -> str:
    safe_path = resolve_workspace_path(path, must_exist=False)
    if safe_path.exists() and safe_path.is_dir():
        raise IsADirectoryError(f"Not a file: {relative_to_workspace(safe_path)}")
    resolve_workspace_path(safe_path.parent, must_exist=True)
    safe_path.write_text(content)
    return "file_written"


def list_files(path: str = ".") -> List[str]:
    safe_path = resolve_workspace_path(path, must_exist=False)
    if not safe_path.exists():
        return []
    if safe_path.is_file():
        return [relative_to_workspace(safe_path)]
    return [relative_to_workspace(item) for item in sorted(safe_path.rglob("*"))]
