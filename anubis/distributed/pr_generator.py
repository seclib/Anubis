"""Autonomous pull request generation for ANUBIS Level 3."""

from __future__ import annotations

import asyncio
import json
import re
import shlex
from dataclasses import dataclass, field
from enum import StrEnum
from inspect import isawaitable
from typing import Any

from anubis.distributed.contracts import EventType, OrchestrationEvent
from anubis.distributed.event_bus import EventBus
from anubis.distributed.feature_engine import FeatureEngineResult
from anubis.distributed.git_agent import DiffAnalysis, GitAutonomyResult, GitStage
from anubis.distributed.task_graph import NodeExecutionResult, TaskGraphNode, TaskGraphNodeType
from anubis.distributed.worker_pool import ExecutorWorkerPool


class PRStage(StrEnum):
    VALIDATING = "validating"
    SUMMARIZING = "summarizing"
    READY = "ready"
    CREATED = "created"
    FAILED = "failed"


@dataclass(frozen=True)
class LinkedWorkItem:
    identifier: str
    kind: str = "task"

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class ValidationEvidence:
    success: bool
    checks: tuple[dict[str, Any], ...]
    source: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "checks": [dict(check) for check in self.checks],
            "source": self.source,
            "error": self.error,
        }


@dataclass(frozen=True)
class CodeSummary:
    changes: tuple[str, ...]
    modifications: tuple[str, ...]
    risks: tuple[str, ...]
    test_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "changes": list(self.changes),
            "modifications": list(self.modifications),
            "risks": list(self.risks),
            "test_summary": self.test_summary,
        }


@dataclass(frozen=True)
class PullRequestPayload:
    title: str
    body: str
    head_branch: str
    base_branch: str
    linked_items: tuple[LinkedWorkItem, ...] = ()
    labels: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "head_branch": self.head_branch,
            "base_branch": self.base_branch,
            "linked_items": [item.to_dict() for item in self.linked_items],
            "labels": list(self.labels),
        }


@dataclass(frozen=True)
class PRGenerationRequest:
    task_id: str
    goal: str
    git_result: GitAutonomyResult | None = None
    feature_result: FeatureEngineResult | None = None
    base_branch: str = "main"
    head_branch: str | None = None
    repo_path: str = "."
    linked_items: tuple[LinkedWorkItem, ...] = ()
    validation_commands: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    create_remote: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "git_result": self.git_result.to_dict() if self.git_result else None,
            "feature_result": self.feature_result.to_dict() if self.feature_result else None,
            "base_branch": self.base_branch,
            "head_branch": self.head_branch,
            "repo_path": self.repo_path,
            "linked_items": [item.to_dict() for item in self.linked_items],
            "validation_commands": list(self.validation_commands),
            "labels": list(self.labels),
            "create_remote": self.create_remote,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PRGenerationResult:
    task_id: str
    success: bool
    stage: PRStage
    payload: PullRequestPayload | None = None
    summary: CodeSummary | None = None
    validation: ValidationEvidence | None = None
    creation_result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "stage": self.stage.value,
            "payload": self.payload.to_dict() if self.payload else None,
            "summary": self.summary.to_dict() if self.summary else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "creation_result": dict(self.creation_result) if self.creation_result else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class PRGeneratorConfig:
    create_remote: bool = True
    default_base_branch: str = "main"
    allow_network: bool = True


class AutonomousPRGenerator:
    """Builds and optionally creates production-ready pull requests."""

    def __init__(
        self,
        *,
        executor_pool: ExecutorWorkerPool | None = None,
        event_bus: EventBus | None = None,
        config: PRGeneratorConfig | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.executor_pool = executor_pool or ExecutorWorkerPool(max_workers=1, event_bus=self.event_bus)
        self.config = config or PRGeneratorConfig()

    async def run(self, request: PRGenerationRequest) -> PRGenerationResult:
        try:
            self._validate_request(request)
            await self._publish(request.task_id, PRStage.VALIDATING, "Validating PR readiness")
            validation = await self.validate(request)
            if not validation.success:
                return await self._failed(request.task_id, "validation failed before PR creation", validation=validation)

            await self._publish(request.task_id, PRStage.SUMMARIZING, "Generating PR code summary")
            summary = self.summarize(request, validation)
            payload = self.build_payload(request, summary)
            await self._publish(request.task_id, PRStage.READY, "Pull request payload ready", {"payload": payload.to_dict()})

            should_create = self.config.create_remote if request.create_remote is None else request.create_remote
            if not should_create:
                return PRGenerationResult(
                    task_id=request.task_id,
                    success=True,
                    stage=PRStage.READY,
                    payload=payload,
                    summary=summary,
                    validation=validation,
                )

            creation_result = await self.create_pull_request(request, payload)
            if not creation_result["success"]:
                return await self._failed(
                    request.task_id,
                    "pull request creation failed",
                    payload=payload,
                    summary=summary,
                    validation=validation,
                    creation_result=creation_result,
                )
            await self._publish(request.task_id, PRStage.CREATED, "Pull request created", {"creation": creation_result})
            return PRGenerationResult(
                task_id=request.task_id,
                success=True,
                stage=PRStage.CREATED,
                payload=payload,
                summary=summary,
                validation=validation,
                creation_result=creation_result,
            )
        except Exception as exc:
            return await self._failed(request.task_id, f"{exc.__class__.__name__}: {exc}")

    def run_sync(self, request: PRGenerationRequest) -> PRGenerationResult:
        return asyncio.run(self.run(request))

    async def validate(self, request: PRGenerationRequest) -> ValidationEvidence:
        if request.validation_commands:
            return await self._run_validation_commands(request)

        checks: list[dict[str, Any]] = []
        if request.feature_result is not None:
            checks.extend(self._feature_validation_checks(request.feature_result))
        if request.git_result is not None:
            checks.append(
                {
                    "name": "git_push",
                    "success": request.git_result.success and request.git_result.stage == GitStage.PUSHED,
                    "stage": request.git_result.stage.value,
                    "error": request.git_result.error,
                }
            )

        if not checks:
            return ValidationEvidence(
                success=False,
                checks=(),
                source="none",
                error="no validation evidence provided",
            )
        return ValidationEvidence(
            success=all(bool(check.get("success")) for check in checks),
            checks=tuple(checks),
            source="evidence",
        )

    def summarize(self, request: PRGenerationRequest, validation: ValidationEvidence) -> CodeSummary:
        diffs = self._diffs(request)
        files = tuple(dict.fromkeys(file for diff in diffs for file in diff.changed_files))
        commits = tuple(commit.message for commit in request.git_result.commits) if request.git_result else ()
        changes = commits or (request.goal.strip(),)
        modifications = files or self._modifications_from_feature(request.feature_result)
        risks = self._risks(diffs, request, validation)
        test_count = len(validation.checks)
        passed_count = sum(1 for check in validation.checks if check.get("success"))
        return CodeSummary(
            changes=tuple(changes),
            modifications=tuple(modifications),
            risks=tuple(risks),
            test_summary=f"{passed_count}/{test_count} validation check(s) passed",
        )

    def build_payload(self, request: PRGenerationRequest, summary: CodeSummary) -> PullRequestPayload:
        linked_items = request.linked_items or self._linked_items(request)
        head_branch = self._head_branch(request)
        title = self.title(request)
        body = self.description(request, summary, linked_items)
        return PullRequestPayload(
            title=title,
            body=body,
            head_branch=head_branch,
            base_branch=request.base_branch or self.config.default_base_branch,
            linked_items=linked_items,
            labels=request.labels,
        )

    def title(self, request: PRGenerationRequest) -> str:
        if request.git_result and request.git_result.commits:
            return _sentence(request.git_result.commits[0].message.split(":", 1)[-1].strip())
        return _sentence(request.goal)

    def description(
        self,
        request: PRGenerationRequest,
        summary: CodeSummary,
        linked_items: tuple[LinkedWorkItem, ...],
    ) -> str:
        linked = "\n".join(f"- {item.kind}: {item.identifier}" for item in linked_items) or "- none"
        changes = "\n".join(f"- {change}" for change in summary.changes) or "- none"
        modifications = "\n".join(f"- {modification}" for modification in summary.modifications) or "- none"
        risks = "\n".join(f"- {risk}" for risk in summary.risks) or "- none identified"
        return (
            "## Summary\n"
            f"{request.goal.strip()}\n\n"
            "## Changes\n"
            f"{changes}\n\n"
            "## Modified Areas\n"
            f"{modifications}\n\n"
            "## Validation\n"
            f"- {summary.test_summary}\n\n"
            "## Risks\n"
            f"{risks}\n\n"
            "## Linked Work\n"
            f"{linked}"
        )

    async def create_pull_request(self, request: PRGenerationRequest, payload: PullRequestPayload) -> dict[str, Any]:
        command = self._create_command(payload)
        node = TaskGraphNode(
            id=f"{request.task_id}:pr:create",
            type=TaskGraphNodeType.EXECUTE,
            payload={
                "task_id": request.task_id,
                "tool": "run_command",
                "input": {
                    "cmd": command,
                    "cwd": request.repo_path,
                    "allow_network": self.config.allow_network,
                },
                "lock_key": f"pr:{request.repo_path}",
            },
        )
        result = await self.executor_pool.node_runner(node)
        return {
            "success": result.success,
            "command": command,
            "output": result.output,
            "error": result.error,
        }

    async def _run_validation_commands(self, request: PRGenerationRequest) -> ValidationEvidence:
        checks: list[dict[str, Any]] = []
        for index, command in enumerate(request.validation_commands, start=1):
            node = TaskGraphNode(
                id=f"{request.task_id}:pr:validate:{index:03d}",
                type=TaskGraphNodeType.EXECUTE,
                payload={
                    "task_id": request.task_id,
                    "tool": "run_command",
                    "input": {"cmd": command, "cwd": request.repo_path},
                    "lock_key": f"cwd:{request.repo_path}",
                },
            )
            result = await self.executor_pool.node_runner(node)
            checks.append(
                {
                    "name": command,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                }
            )
        return ValidationEvidence(
            success=all(check["success"] for check in checks),
            checks=tuple(checks),
            source="commands",
        )

    def _feature_validation_checks(self, feature_result: FeatureEngineResult) -> tuple[dict[str, Any], ...]:
        checks: list[dict[str, Any]] = [
            {
                "name": "feature_engine",
                "success": feature_result.success,
                "stage": feature_result.stage.value,
                "error": feature_result.error,
            }
        ]
        for route in feature_result.route_results:
            for run in route.runs:
                for node_result in run.results:
                    if ":test:" in node_result.node_id or node_result.node_id.endswith(":test"):
                        checks.append(
                            {
                                "name": node_result.node_id,
                                "repo_id": route.repo_id,
                                "success": node_result.success,
                                "output": node_result.output,
                                "error": node_result.error,
                            }
                        )
        return tuple(checks)

    def _diffs(self, request: PRGenerationRequest) -> tuple[DiffAnalysis, ...]:
        if request.git_result and request.git_result.diff:
            return (request.git_result.diff,)
        return ()

    def _modifications_from_feature(self, feature_result: FeatureEngineResult | None) -> tuple[str, ...]:
        if feature_result is None:
            return ()
        modifications: list[str] = []
        for route in feature_result.route_results:
            modifications.append(route.repo_id)
        return tuple(dict.fromkeys(modifications))

    def _risks(
        self,
        diffs: tuple[DiffAnalysis, ...],
        request: PRGenerationRequest,
        validation: ValidationEvidence,
    ) -> tuple[str, ...]:
        risks: list[str] = []
        for diff in diffs:
            if diff.risk != "low":
                risks.append(f"{diff.risk} diff risk: {diff.summary}")
            for path in diff.changed_files:
                if path.endswith((".lock", ".sql")) or path in {"package.json", "pyproject.toml", "Dockerfile"}:
                    risks.append(f"sensitive file changed: {path}")
        if request.git_result and request.git_result.stage != GitStage.PUSHED:
            risks.append(f"branch not pushed automatically: {request.git_result.stage.value}")
        if not validation.success:
            risks.append("validation did not pass")
        return tuple(dict.fromkeys(risks))

    def _head_branch(self, request: PRGenerationRequest) -> str:
        if request.head_branch:
            return request.head_branch
        if request.git_result and request.git_result.branch:
            return request.git_result.branch.name
        raise ValueError("head branch is required when git result has no branch")

    def _linked_items(self, request: PRGenerationRequest) -> tuple[LinkedWorkItem, ...]:
        items: list[LinkedWorkItem] = []
        for token in re.findall(r"(?:#\d+|[A-Z][A-Z0-9]+-\d+)", request.goal):
            kind = "issue" if token.startswith("#") else "task"
            items.append(LinkedWorkItem(identifier=token, kind=kind))
        return tuple(dict.fromkeys(items))

    def _create_command(self, payload: PullRequestPayload) -> str:
        labels = " ".join(f"--label {shlex.quote(label)}" for label in payload.labels)
        command = (
            "gh pr create "
            f"--title {shlex.quote(payload.title)} "
            f"--body {shlex.quote(payload.body)} "
            f"--head {shlex.quote(payload.head_branch)} "
            f"--base {shlex.quote(payload.base_branch)}"
        )
        return f"{command} {labels}".strip()

    def _validate_request(self, request: PRGenerationRequest) -> None:
        if not request.task_id.strip():
            raise ValueError("task_id is required")
        if not request.goal.strip():
            raise ValueError("goal is required")
        if not request.repo_path.strip():
            raise ValueError("repo_path is required")

    async def _failed(
        self,
        task_id: str,
        error: str,
        *,
        payload: PullRequestPayload | None = None,
        summary: CodeSummary | None = None,
        validation: ValidationEvidence | None = None,
        creation_result: dict[str, Any] | None = None,
    ) -> PRGenerationResult:
        await self._publish(task_id, PRStage.FAILED, error)
        return PRGenerationResult(
            task_id=task_id,
            success=False,
            stage=PRStage.FAILED,
            payload=payload,
            summary=summary,
            validation=validation,
            creation_result=creation_result,
            error=error,
        )

    async def _publish(
        self,
        task_id: str,
        stage: PRStage,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = OrchestrationEvent(
            event_type=EventType.TASK_FAILED if stage == PRStage.FAILED else EventType.TASK_STATE_CHANGED,
            task_id=task_id,
            message=message,
            payload={"stage": stage.value, **(payload or {})},
        )
        published = self.event_bus.publish(event)
        if isawaitable(published):
            await published


def _sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    if not text:
        return "Autonomous software update"
    text = text[0].upper() + text[1:]
    return text[:90]


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


__all__ = [
    "AutonomousPRGenerator",
    "CodeSummary",
    "LinkedWorkItem",
    "PRGenerationRequest",
    "PRGenerationResult",
    "PRGeneratorConfig",
    "PRStage",
    "PullRequestPayload",
    "ValidationEvidence",
]
