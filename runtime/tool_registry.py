"""Concrete tool registry for the default CLI runtime."""

from __future__ import annotations

from collections.abc import Mapping

from config import OBSIDIAN_RAG_ENABLED, OSINT_CRAWLER_ENABLED
from executor.tool_executor import ToolExecutor, ToolFunction
from runtime.plugins import PluginManager, builtin_tool_plugin
from tools.autonomous_developer import (
    create_project_scaffold,
    developer_autonomy_plan,
    developer_project_status,
    install_project_dependencies,
    run_project_build,
    run_project_tests,
    start_project_server,
    stop_project_server,
)
from tools.dynamic_tools import (
    DynamicToolError,
    create_dynamic_tool,
    dynamic_tool_specs,
    list_dynamic_tools,
    load_dynamic_tools,
)
from tools.filesystem import list_files, read_file, write_file
from tools.git_autonomy import (
    autonomous_git_commit,
    generate_commit_message,
    git_status,
    rollback_last_autonomous_commit,
    run_git_validations,
)
from tools.hermes_memory import (
    append_daily_memory_summary,
    index_obsidian_vault,
    search_hermes_memory,
    store_hermes_memory,
    write_obsidian_note,
)
from tools.osint import crawl_osint_sources, fetch_external_data
from tools.repo import (
    detect_project_type,
    find_entrypoints,
    find_file,
    get_file_tree,
    scan_repo_tree,
    search_code,
)
from tools.sandbox import SandboxViolation, audit_tool_action
from tools.terminal import run_command
from tools.vector_memory import (
    index_repository,
    retrieve_context,
    semantic_search,
)

_REGISTRY: dict[str, ToolFunction] | None = None
_EXECUTOR: ToolExecutor | None = None
_PLUGINS: PluginManager | None = None


class _RuntimeToolRegistry(dict[str, ToolFunction]):
    def _load(self) -> None:
        if dict.__len__(self) == 0:
            dict.update(self, tool_registry())

    def __contains__(self, key: object) -> bool:
        self._load()
        return dict.__contains__(self, key)

    def __iter__(self):
        self._load()
        return dict.__iter__(self)

    def __len__(self) -> int:
        self._load()
        return dict.__len__(self)

    def __getitem__(self, key: str) -> ToolFunction:
        self._load()
        return dict.__getitem__(self, key)

    def items(self):
        self._load()
        return dict.items(self)

    def keys(self):
        self._load()
        return dict.keys(self)

    def values(self):
        self._load()
        return dict.values(self)


TOOLS: dict[str, ToolFunction] = _RuntimeToolRegistry()


def build_tool_registry() -> dict[str, ToolFunction]:
    """Build the concrete tool registry used by the default runtime."""
    builtin_tools = {
        "read_file": read_file,
        "write_file": write_file,
        "list_files": list_files,
        "run_command": run_command,
        "search_code": search_code,
        "scan_repo_tree": scan_repo_tree,
        "detect_project_type": detect_project_type,
        "find_entrypoints": find_entrypoints,
        "find_file": find_file,
        "get_file_tree": get_file_tree,
        "index_repository": index_repository,
        "semantic_search": semantic_search,
        "retrieve_context": retrieve_context,
        "git_status": git_status,
        "generate_commit_message": generate_commit_message,
        "run_git_validations": run_git_validations,
        "autonomous_git_commit": autonomous_git_commit,
        "rollback_last_autonomous_commit": rollback_last_autonomous_commit,
        "create_dynamic_tool": create_dynamic_tool,
        "list_dynamic_tools": list_dynamic_tools,
        "developer_project_status": developer_project_status,
        "developer_autonomy_plan": developer_autonomy_plan,
        "create_project_scaffold": create_project_scaffold,
        "install_project_dependencies": install_project_dependencies,
        "run_project_build": run_project_build,
        "run_project_tests": run_project_tests,
        "start_project_server": start_project_server,
        "stop_project_server": stop_project_server,
    }
    if OBSIDIAN_RAG_ENABLED:
        builtin_tools.update(
            {
                "search_hermes_memory": search_hermes_memory,
                "index_obsidian_vault": index_obsidian_vault,
                "store_hermes_memory": store_hermes_memory,
                "write_obsidian_note": write_obsidian_note,
                "append_daily_memory_summary": append_daily_memory_summary,
            }
        )
    if OSINT_CRAWLER_ENABLED:
        builtin_tools["fetch_external_data"] = fetch_external_data
        builtin_tools["crawl_osint_sources"] = crawl_osint_sources
    plugins = plugin_manager()
    if not any(plugin["name"] == "builtin" for plugin in plugins.manifest()):
        plugins.register(builtin_tool_plugin(builtin_tools))
    return plugins.tools()


def plugin_manager() -> PluginManager:
    global _PLUGINS
    if _PLUGINS is None:
        _PLUGINS = PluginManager()
    return _PLUGINS


def tool_registry() -> dict[str, ToolFunction]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_tool_registry()
        TOOLS.clear()
        TOOLS.update(_REGISTRY)
    return _REGISTRY


def tool_names() -> list[str]:
    return sorted(tool_registry())


def default_tool_executor() -> ToolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = ToolExecutor(
            tool_registry(),
            audit=audit_tool_action,
            dynamic_loader=load_dynamic_tools,
            sandbox_error=SandboxViolation,
            dynamic_tool_error=DynamicToolError,
        )
    return _EXECUTOR


def refresh_dynamic_tools() -> Mapping[str, ToolFunction]:
    dynamic_tools = default_tool_executor().refresh_dynamic_tools()
    tool_registry().update(dynamic_tools)
    TOOLS.clear()
    TOOLS.update(tool_registry())
    TOOLS.update(default_tool_executor().tools)
    return dynamic_tools


def execute_tool(tool: str, args: Mapping[str, object] | None = None) -> dict[str, object]:
    """Execute a concrete runtime tool through the default executor."""
    return default_tool_executor().execute(tool, args)


def runtime_tool_specs() -> Mapping[str, object]:
    return dynamic_tool_specs()


__all__ = [
    "build_tool_registry",
    "default_tool_executor",
    "execute_tool",
    "plugin_manager",
    "refresh_dynamic_tools",
    "runtime_tool_specs",
    "TOOLS",
    "tool_names",
    "tool_registry",
]
