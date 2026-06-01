from __future__ import annotations

from pathlib import Path

from anubis_tools.sandbox.schemas import ToolPermission


class PermissionDenied(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PermissionRegistry:
    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root.resolve()
        self._permissions: dict[str, ToolPermission] = {
            "web.search": ToolPermission(network=True, filesystem=False, shell=False),
            "file.read": ToolPermission(
                network=False,
                filesystem="read_only",
                shell=False,
                allowed_paths=[str(self._workspace_root)],
            ),
            "note.write": ToolPermission(
                network=False,
                filesystem="read_write",
                shell=False,
                allowed_paths=[str(self._workspace_root)],
            ),
            "memory.retrieve": ToolPermission(network=False, filesystem=False, shell=False),
        }

    def get(self, tool_name: str) -> ToolPermission:
        permission = self._permissions.get(tool_name)
        if permission is None:
            raise PermissionDenied("UNKNOWN_TOOL", "Tool is not registered in the permission registry")
        if permission.shell:
            raise PermissionDenied("SHELL_DENIED", "Shell access is not permitted for tools")
        return permission

    def assert_allowed(self, tool_name: str, parameters: dict) -> ToolPermission:
        permission = self.get(tool_name)
        if not permission.allowed_paths:
            return permission

        path_value = parameters.get("relative_path") or parameters.get("path") or parameters.get("folder")
        if not path_value:
            return permission
        candidate = (self._workspace_root / str(path_value)).resolve()
        if candidate == self._workspace_root:
            return permission
        if self._workspace_root not in candidate.parents:
            raise PermissionDenied("PATH_DENIED", "Requested path escapes the sandbox workspace")
        return permission
