"""Dynamic Python tool creation and loading."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Callable

from tools.sandbox import relative_to_workspace, resolve_workspace_path

ToolCallable = Callable[..., Any]

GENERATED_TOOLS_DIR = "tools/generated"
TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{2,63}$")
FORBIDDEN_CALLS = {"eval", "exec", "compile", "open", "input", "__import__"}
FORBIDDEN_IMPORT_ROOTS = {
    "asyncio",
    "ctypes",
    "multiprocessing",
    "os",
    "pathlib",
    "pty",
    "requests",
    "shutil",
    "socket",
    "subprocess",
    "sys",
    "threading",
}
ALLOWED_IMPORT_ROOTS = {
    "collections",
    "datetime",
    "functools",
    "itertools",
    "json",
    "math",
    "re",
    "statistics",
    "typing",
    "tools.filesystem",
    "tools.repo",
    "tools.sandbox",
}


class DynamicToolError(ValueError):
    """Raised when a dynamic tool cannot be created or loaded safely."""


def _dynamic_root() -> Path:
    root = resolve_workspace_path(GENERATED_TOOLS_DIR, must_exist=False)
    root.mkdir(parents=True, exist_ok=True)
    init_file = root / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""Generated Anubis tools."""\n')
    return root


def _metadata_path(tool_name: str) -> Path:
    return _dynamic_root() / f"{tool_name}.json"


def _tool_path(tool_name: str) -> Path:
    return _dynamic_root() / f"{tool_name}.py"


def _validate_tool_name(tool_name: str) -> str:
    normalized = str(tool_name or "").strip()
    if not TOOL_NAME_PATTERN.match(normalized):
        raise DynamicToolError(
            "Tool name must be a valid Python identifier with 3-64 characters."
        )
    if normalized.startswith("_"):
        raise DynamicToolError("Tool name must not start with an underscore.")
    return normalized


def _import_root(name: str) -> str:
    parts = name.split(".")
    if len(parts) >= 2 and parts[0] == "tools":
        return ".".join(parts[:2])
    return parts[0]


def _validate_import(name: str) -> None:
    root = _import_root(name)
    if root in FORBIDDEN_IMPORT_ROOTS:
        raise DynamicToolError(f"Import is not allowed in dynamic tool: {name}")
    if root not in ALLOWED_IMPORT_ROOTS:
        raise DynamicToolError(f"Import is not whitelisted in dynamic tool: {name}")


def _validate_code(code: str) -> None:
    if not isinstance(code, str) or not code.strip():
        raise DynamicToolError("Dynamic tool code must be non-empty.")

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise DynamicToolError(f"Dynamic tool syntax error: {exc}") from exc

    has_run = any(isinstance(node, ast.FunctionDef) and node.name == "run" for node in tree.body)
    if not has_run:
        raise DynamicToolError("Dynamic tool must define a top-level run(**kwargs) function.")

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        raise DynamicToolError("Dynamic tools may only define imports, docstrings, and functions at top level.")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _validate_import(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                raise DynamicToolError("Relative imports are not allowed in dynamic tools.")
            _validate_import(node.module)
        elif isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name) and function.id in FORBIDDEN_CALLS:
                raise DynamicToolError(f"Call is not allowed in dynamic tool: {function.id}")
            if isinstance(function, ast.Attribute) and function.attr in FORBIDDEN_CALLS:
                raise DynamicToolError(f"Call is not allowed in dynamic tool: {function.attr}")


def _load_tool_callable(tool_name: str, path: Path) -> ToolCallable:
    module_name = f"tools.generated.{tool_name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise DynamicToolError(f"Cannot load dynamic tool module: {relative_to_workspace(path)}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = getattr(module, "run", None)
    if not callable(run):
        raise DynamicToolError(f"Dynamic tool has no callable run function: {tool_name}")
    return run


def create_dynamic_tool(
    tool_name: str,
    code: str,
    description: str = "",
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or replace a generated Python tool under ``tools/generated``."""
    normalized_name = _validate_tool_name(tool_name)
    _validate_code(code)

    path = _tool_path(normalized_name)
    metadata = {
        "tool_name": normalized_name,
        "description": str(description or ""),
        "schema": schema or {},
        "path": relative_to_workspace(path),
    }
    path.write_text(code.rstrip() + "\n")
    _metadata_path(normalized_name).write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str)
    )
    _load_tool_callable(normalized_name, path)
    return {
        "status": "created",
        "tool_name": normalized_name,
        "path": metadata["path"],
        "description": metadata["description"],
        "schema": metadata["schema"],
    }


def _load_metadata(tool_name: str) -> dict[str, Any]:
    path = _metadata_path(tool_name)
    if not path.exists():
        return {
            "tool_name": tool_name,
            "description": "",
            "schema": {},
            "path": relative_to_workspace(_tool_path(tool_name)),
        }
    try:
        data = json.loads(path.read_text())
    except Exception:
        data = {}
    return {
        "tool_name": str(data.get("tool_name") or tool_name),
        "description": str(data.get("description") or ""),
        "schema": data.get("schema") if isinstance(data.get("schema"), dict) else {},
        "path": str(data.get("path") or relative_to_workspace(_tool_path(tool_name))),
    }


def load_dynamic_tools() -> dict[str, ToolCallable]:
    """Load all valid generated tools from disk."""
    tools: dict[str, ToolCallable] = {}
    for path in sorted(_dynamic_root().glob("*.py")):
        if path.name == "__init__.py":
            continue
        tool_name = path.stem
        try:
            _validate_tool_name(tool_name)
            _validate_code(path.read_text())
            tools[tool_name] = _load_tool_callable(tool_name, path)
        except DynamicToolError:
            continue
    return tools


def list_dynamic_tools() -> list[dict[str, Any]]:
    """Return metadata for generated tools that can currently be loaded."""
    loaded = load_dynamic_tools()
    return [_load_metadata(tool_name) for tool_name in sorted(loaded)]


def dynamic_tool_specs() -> dict[str, dict[str, Any]]:
    """Return generated tool schemas for prompt/tool registry display."""
    specs: dict[str, dict[str, Any]] = {}
    for metadata in list_dynamic_tools():
        schema = metadata.get("schema") if isinstance(metadata.get("schema"), dict) else {}
        specs[str(metadata["tool_name"])] = schema or {"kwargs": "<dynamic tool args>"}
    return specs


__all__ = [
    "DynamicToolError",
    "create_dynamic_tool",
    "dynamic_tool_specs",
    "list_dynamic_tools",
    "load_dynamic_tools",
]
