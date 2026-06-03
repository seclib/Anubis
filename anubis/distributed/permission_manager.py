"""Role-based tool permission system for ANUBIS security layer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from anubis.distributed.contracts import AgentType


class ToolCategory(StrEnum):
    FILESYSTEM = "filesystem"
    SHELL = "shell"
    GIT = "git"
    NETWORK = "network"
    ANALYSIS = "analysis"


class ToolAccessLevel(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class ToolPermissionStatus(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    category: ToolCategory
    access: ToolAccessLevel
    requires_sandbox: bool = True
    network_restricted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category.value,
            "access": self.access.value,
            "requires_sandbox": self.requires_sandbox,
            "network_restricted": self.network_restricted,
        }


@dataclass(frozen=True)
class ToolExecutionContext:
    agent_type: AgentType | str
    task_id: str
    sandboxed: bool = False
    sandbox_id: str | None = None
    workspace: str | None = None
    allow_network: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def role(self) -> str:
        return self.agent_type.value if isinstance(self.agent_type, AgentType) else str(self.agent_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_type": self.role,
            "task_id": self.task_id,
            "sandboxed": self.sandboxed,
            "sandbox_id": self.sandbox_id,
            "workspace": self.workspace,
            "allow_network": self.allow_network,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PermissionDecision:
    status: ToolPermissionStatus
    tool: str
    agent_type: str
    reason: str
    category: ToolCategory | None = None
    access: ToolAccessLevel | None = None

    @property
    def approved(self) -> bool:
        return self.status == ToolPermissionStatus.APPROVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "approved": self.approved,
            "tool": self.tool,
            "agent_type": self.agent_type,
            "reason": self.reason,
            "category": self.category.value if self.category else None,
            "access": self.access.value if self.access else None,
        }


@dataclass(frozen=True)
class RolePermission:
    categories: frozenset[ToolCategory] = field(default_factory=frozenset)
    tools: frozenset[str] = field(default_factory=frozenset)
    read_only: bool = False
    require_sandbox: bool = True


DEFAULT_TOOL_DEFINITIONS: dict[str, ToolDefinition] = {
    "read_file": ToolDefinition("read_file", ToolCategory.FILESYSTEM, ToolAccessLevel.READ),
    "write_file": ToolDefinition("write_file", ToolCategory.FILESYSTEM, ToolAccessLevel.WRITE),
    "search_codebase": ToolDefinition("search_codebase", ToolCategory.ANALYSIS, ToolAccessLevel.READ),
    "run_command": ToolDefinition("run_command", ToolCategory.SHELL, ToolAccessLevel.EXECUTE),
    "git_diff": ToolDefinition("git_diff", ToolCategory.GIT, ToolAccessLevel.READ),
    "git_commit": ToolDefinition("git_commit", ToolCategory.GIT, ToolAccessLevel.WRITE),
    "http_get": ToolDefinition("http_get", ToolCategory.NETWORK, ToolAccessLevel.READ, network_restricted=True),
    "web_search": ToolDefinition("web_search", ToolCategory.NETWORK, ToolAccessLevel.READ, network_restricted=True),
}


DEFAULT_ROLE_PERMISSIONS: dict[str, RolePermission] = {
    AgentType.PLANNER.value: RolePermission(
        categories=frozenset({ToolCategory.FILESYSTEM, ToolCategory.ANALYSIS}),
        tools=frozenset({"read_file", "search_codebase"}),
        read_only=True,
        require_sandbox=True,
    ),
    AgentType.EXECUTOR.value: RolePermission(
        categories=frozenset({ToolCategory.FILESYSTEM, ToolCategory.SHELL, ToolCategory.ANALYSIS}),
        tools=frozenset({"read_file", "write_file", "search_codebase", "run_command"}),
        read_only=False,
        require_sandbox=True,
    ),
    AgentType.REVIEWER.value: RolePermission(
        categories=frozenset({ToolCategory.FILESYSTEM, ToolCategory.ANALYSIS}),
        tools=frozenset({"read_file", "search_codebase"}),
        read_only=True,
        require_sandbox=True,
    ),
}


class PermissionManager:
    """Evaluates role-based tool permissions with deny-by-default semantics."""

    def __init__(
        self,
        *,
        tools: Mapping[str, ToolDefinition] | None = None,
        role_permissions: Mapping[str, RolePermission] | None = None,
    ) -> None:
        self.tools = dict(tools or DEFAULT_TOOL_DEFINITIONS)
        self.role_permissions = dict(role_permissions or DEFAULT_ROLE_PERMISSIONS)

    def check(self, tool: str, context: ToolExecutionContext) -> PermissionDecision:
        role = context.role
        definition = self.tools.get(tool)
        if definition is None:
            return self._deny(tool, role, "tool is not registered")

        role_permission = self.role_permissions.get(role)
        if role_permission is None:
            return self._deny(tool, role, "agent role has no permissions", definition)
        if tool not in role_permission.tools:
            return self._deny(tool, role, "tool is not explicitly allowed for role", definition)
        if definition.category not in role_permission.categories:
            return self._deny(tool, role, "tool category is not allowed for role", definition)
        if role_permission.read_only and definition.access != ToolAccessLevel.READ:
            return self._deny(tool, role, "role is read-only", definition)
        if (definition.requires_sandbox or role_permission.require_sandbox) and not context.sandboxed:
            return self._deny(tool, role, "sandbox context is required", definition)
        if definition.network_restricted and not context.allow_network:
            return self._deny(tool, role, "network access is restricted", definition)
        if not context.task_id.strip():
            return self._deny(tool, role, "task_id is required", definition)

        return PermissionDecision(
            status=ToolPermissionStatus.APPROVED,
            tool=tool,
            agent_type=role,
            reason="approved",
            category=definition.category,
            access=definition.access,
        )

    def approve_or_raise(self, tool: str, context: ToolExecutionContext) -> PermissionDecision:
        decision = self.check(tool, context)
        if not decision.approved:
            raise PermissionError(decision.reason)
        return decision

    def _deny(
        self,
        tool: str,
        role: str,
        reason: str,
        definition: ToolDefinition | None = None,
    ) -> PermissionDecision:
        return PermissionDecision(
            status=ToolPermissionStatus.DENIED,
            tool=tool,
            agent_type=role,
            reason=reason,
            category=definition.category if definition else None,
            access=definition.access if definition else None,
        )


class ToolGatekeeper:
    """Pre-execution permission gate for tool calls."""

    def __init__(self, permission_manager: PermissionManager | None = None) -> None:
        self.permission_manager = permission_manager or PermissionManager()
        self.decisions: list[PermissionDecision] = []

    def approve(self, tool: str, context: ToolExecutionContext) -> PermissionDecision:
        decision = self.permission_manager.check(tool, context)
        self.decisions.append(decision)
        return decision

    def approve_or_reject(self, tool: str, context: ToolExecutionContext) -> dict[str, Any]:
        decision = self.approve(tool, context)
        return decision.to_dict()

    def history(self) -> tuple[PermissionDecision, ...]:
        return tuple(self.decisions)


class PermissionedToolIntegrationLayer:
    """ToolIntegrationLayer-compatible wrapper that gates calls before execution."""

    def __init__(
        self,
        *,
        delegate: Any,
        context: ToolExecutionContext,
        gatekeeper: ToolGatekeeper | None = None,
    ) -> None:
        self.delegate = delegate
        self.context = context
        self.gatekeeper = gatekeeper or ToolGatekeeper()

    def execute(self, tool: str, tool_input: Mapping[str, Any] | None = None) -> dict[str, Any]:
        decision = self.gatekeeper.approve(tool, self.context)
        if not decision.approved:
            return {
                "tool": tool,
                "input": dict(tool_input or {}),
                "output": decision.reason,
                "success": False,
                "logs": [f"permission denied: {decision.reason}"],
                "permission": decision.to_dict(),
            }
        result = self.delegate.execute(tool, dict(tool_input or {}))
        if isinstance(result, dict):
            result.setdefault("permission", decision.to_dict())
            return result
        return {
            "tool": tool,
            "input": dict(tool_input or {}),
            "output": result,
            "success": False,
            "logs": [f"Invalid delegated tool result type: {type(result).__name__}"],
            "permission": decision.to_dict(),
        }


__all__ = [
    "DEFAULT_ROLE_PERMISSIONS",
    "DEFAULT_TOOL_DEFINITIONS",
    "PermissionDecision",
    "PermissionManager",
    "PermissionedToolIntegrationLayer",
    "RolePermission",
    "ToolAccessLevel",
    "ToolCategory",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolGatekeeper",
    "ToolPermissionStatus",
]
