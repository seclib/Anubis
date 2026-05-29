"""Workspace path helpers shared outside the tool layer."""

from __future__ import annotations

from pathlib import Path

from config import WORKSPACE_ROOT


class WorkspaceViolation(PermissionError):
    """Raised when a path attempts to leave the configured workspace."""


def workspace_root() -> Path:
    root = Path(WORKSPACE_ROOT).expanduser().resolve()
    if not root.exists():
        raise WorkspaceViolation(f"Workspace root does not exist: {root}")
    if not root.is_dir():
        raise WorkspaceViolation(f"Workspace root is not a directory: {root}")
    return root


def ensure_inside_workspace(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise WorkspaceViolation(f"Path escapes workspace: {path}") from exc


def resolve_workspace_path(path: str | Path = ".", *, must_exist: bool = False) -> Path:
    if path is None:
        path = "."

    raw_path = str(path)
    if "\x00" in raw_path:
        raise WorkspaceViolation("Path contains a null byte")

    root = workspace_root()
    requested_path = Path(raw_path).expanduser()
    candidate = requested_path if requested_path.is_absolute() else root / requested_path
    resolved = candidate.resolve(strict=False)
    ensure_inside_workspace(resolved, root)

    if must_exist and not resolved.exists():
        raise WorkspaceViolation(f"Path does not exist in workspace: {raw_path}")

    return resolved


def relative_to_workspace(path: str | Path) -> str:
    root = workspace_root()
    resolved = resolve_workspace_path(path, must_exist=False)
    return "." if resolved == root else str(resolved.relative_to(root))

