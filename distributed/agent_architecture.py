"""Canonical simplified agent architecture for ANUBIS.

The production runtime has exactly three agent roles. Orchestration, memory,
security, git, CI, and deployment are platform services, not reasoning agents.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from anubis.distributed.contracts import AgentType


class PlatformService(StrEnum):
    ORCHESTRATION = "orchestration_service"
    MEMORY = "memory_service"
    SECURITY = "security_service"
    GIT = "git_service"
    CI_CD = "ci_cd_service"


@dataclass(frozen=True)
class AgentRoleDefinition:
    agent_type: AgentType
    responsibility: str
    owns: tuple[str, ...]
    forbidden: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["agent_type"] = self.agent_type.value
        return payload


@dataclass(frozen=True)
class LegacyAgentMapping:
    legacy_name: str
    target: AgentType | PlatformService
    action: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target"] = self.target.value
        return payload


@dataclass(frozen=True)
class SimplifiedAgentArchitecture:
    roles: tuple[AgentRoleDefinition, ...]
    platform_services: tuple[PlatformService, ...]
    legacy_mappings: tuple[LegacyAgentMapping, ...]
    migration_steps: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "roles": [role.to_dict() for role in self.roles],
            "platform_services": [service.value for service in self.platform_services],
            "legacy_mappings": [mapping.to_dict() for mapping in self.legacy_mappings],
            "migration_steps": list(self.migration_steps),
        }


PLANNER_ROLE = AgentRoleDefinition(
    agent_type=AgentType.PLANNER,
    responsibility="Convert goals into deterministic DAG plans with dependencies and success criteria.",
    owns=("task decomposition", "dependency graph", "execution plan schema", "parallelization opportunities"),
    forbidden=("tool execution", "file modification", "review approval", "rollback decisions"),
)

EXECUTOR_ROLE = AgentRoleDefinition(
    agent_type=AgentType.EXECUTOR,
    responsibility="Execute assigned DAG nodes through the sandboxed tool system only.",
    owns=("file operations", "shell commands", "git tool calls", "test command execution", "step result logs"),
    forbidden=("planning next steps", "self-approval", "policy review", "direct host access"),
)

REVIEWER_ROLE = AgentRoleDefinition(
    agent_type=AgentType.REVIEWER,
    responsibility="Validate executor outputs and approve, retry, or request rollback.",
    owns=("result validation", "test interpretation", "risk scoring", "rollback recommendation", "self-review gates"),
    forbidden=("planning implementation", "tool execution", "code modification"),
)


LEGACY_AGENT_MAPPINGS: tuple[LegacyAgentMapping, ...] = (
    LegacyAgentMapping(
        legacy_name="orchestrator_agent",
        target=PlatformService.ORCHESTRATION,
        action="replace_with_service",
        rationale="Coordination is deterministic platform behavior, not a reasoning role.",
    ),
    LegacyAgentMapping(
        legacy_name="coder_agent",
        target=AgentType.EXECUTOR,
        action="merge",
        rationale="Code writing is execution of assigned steps.",
    ),
    LegacyAgentMapping(
        legacy_name="tester_agent",
        target=AgentType.EXECUTOR,
        action="merge",
        rationale="Running tests is tool execution; interpreting failures belongs to reviewer.",
    ),
    LegacyAgentMapping(
        legacy_name="debugger_agent",
        target=AgentType.REVIEWER,
        action="merge",
        rationale="Failure analysis and retry/rollback recommendation are validation responsibilities.",
    ),
    LegacyAgentMapping(
        legacy_name="memory_agent",
        target=PlatformService.MEMORY,
        action="replace_with_service",
        rationale="Memory is the unified retrieval service, not an autonomous agent.",
    ),
    LegacyAgentMapping(
        legacy_name="critic_agent",
        target=AgentType.REVIEWER,
        action="merge",
        rationale="Critique gates are review policy checks.",
    ),
    LegacyAgentMapping(
        legacy_name="meta_cognition_agent",
        target=AgentType.REVIEWER,
        action="merge",
        rationale="Behavioral drift checks are review/security validation.",
    ),
    LegacyAgentMapping(
        legacy_name="loop_optimizer",
        target=PlatformService.ORCHESTRATION,
        action="replace_with_service",
        rationale="Loop optimization is scheduler/orchestrator policy.",
    ),
)


def simplified_agent_architecture() -> SimplifiedAgentArchitecture:
    return SimplifiedAgentArchitecture(
        roles=(PLANNER_ROLE, EXECUTOR_ROLE, REVIEWER_ROLE),
        platform_services=(
            PlatformService.ORCHESTRATION,
            PlatformService.MEMORY,
            PlatformService.SECURITY,
            PlatformService.GIT,
            PlatformService.CI_CD,
        ),
        legacy_mappings=LEGACY_AGENT_MAPPINGS,
        migration_steps=(
            "Freeze new feature work on legacy reasoning agents under agent/ and backend/agent/.",
            "Route all new distributed work through AgentType.PLANNER, AgentType.EXECUTOR, and AgentType.REVIEWER.",
            "Replace legacy orchestrator_agent calls with DistributedOrchestrator service calls.",
            "Move coder_agent and tester_agent behaviors behind executor step handlers.",
            "Move debugger_agent, critic_agent, and meta_cognition_agent checks into ReviewerAgent validation policies.",
            "Move memory_agent behavior to UnifiedMemoryService retrieval and write APIs.",
            "Deprecate legacy multi-agent prompts after parity tests pass.",
            "Remove legacy modules once no runtime imports or tests depend on them.",
        ),
    )


def target_for_legacy_agent(legacy_name: str) -> AgentType | PlatformService | None:
    normalized = legacy_name.strip().lower()
    for mapping in LEGACY_AGENT_MAPPINGS:
        if mapping.legacy_name == normalized:
            return mapping.target
    return None


__all__ = [
    "AgentRoleDefinition",
    "EXECUTOR_ROLE",
    "LEGACY_AGENT_MAPPINGS",
    "LegacyAgentMapping",
    "PLANNER_ROLE",
    "PlatformService",
    "REVIEWER_ROLE",
    "SimplifiedAgentArchitecture",
    "simplified_agent_architecture",
    "target_for_legacy_agent",
]
