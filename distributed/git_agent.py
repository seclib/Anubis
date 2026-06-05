"""Autonomous Git Agent for ANUBIS distributed execution."""

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
from anubis.distributed.task_graph import NodeExecutionResult, TaskGraphNode, TaskGraphNodeType
from anubis.distributed.worker_pool import ExecutorWorkerPool


class GitStage(StrEnum):
    BRANCH_CREATED = "branch_created"
    DIFF_ANALYZED = "diff_analyzed"
    COMMITTED = "committed"
    PUSHED = "pushed"
    FAILED = "failed"


@dataclass(frozen=True)
class AtomicCommitSpec:
    paths: tuple[str, ...] = ()
    message: str | None = None
    kind: str = "feat"
    scope: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "paths": list(self.paths),
            "message": self.message,
            "kind": self.kind,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class GitAutonomyRequest:
    task_id: str
    description: str
    repo_path: str = "."
    repo_id: str | None = None
    branch_prefix: str = "anubis/task"
    base_branch: str | None = None
    remote: str = "origin"
    changed_paths: tuple[str, ...] = ()
    atomic_commits: tuple[AtomicCommitSpec, ...] = ()
    push: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "repo_path": self.repo_path,
            "repo_id": self.repo_id,
            "branch_prefix": self.branch_prefix,
            "base_branch": self.base_branch,
            "remote": self.remote,
            "changed_paths": list(self.changed_paths),
            "atomic_commits": [commit.to_dict() for commit in self.atomic_commits],
            "push": self.push,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class BranchPlan:
    name: str
    base_branch: str | None
    command: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_branch": self.base_branch,
            "command": self.command,
        }


@dataclass(frozen=True)
class DiffAnalysis:
    changed_files: tuple[str, ...]
    additions: int
    deletions: int
    risk: str
    summary: str
    raw: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed_files": list(self.changed_files),
            "additions": self.additions,
            "deletions": self.deletions,
            "risk": self.risk,
            "summary": self.summary,
            "raw": self.raw,
        }


@dataclass(frozen=True)
class CommitPlan:
    message: str
    paths: tuple[str, ...]
    stage_command: str
    commit_command: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "paths": list(self.paths),
            "stage_command": self.stage_command,
            "commit_command": self.commit_command,
        }


@dataclass(frozen=True)
class GitAutonomyResult:
    task_id: str
    success: bool
    stage: GitStage
    branch: BranchPlan | None = None
    diff: DiffAnalysis | None = None
    commits: tuple[CommitPlan, ...] = ()
    push_result: dict[str, Any] | None = None
    operations: tuple[dict[str, Any], ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "stage": self.stage.value,
            "branch": self.branch.to_dict() if self.branch else None,
            "diff": self.diff.to_dict() if self.diff else None,
            "commits": [commit.to_dict() for commit in self.commits],
            "push_result": dict(self.push_result) if self.push_result else None,
            "operations": [dict(operation) for operation in self.operations],
            "error": self.error,
        }


@dataclass(frozen=True)
class GitAgentConfig:
    default_branch_prefix: str = "anubis/task"
    default_remote: str = "origin"
    push_allow_network: bool = True


class GitAgent:
    """Coordinates autonomous Git operations through executor tools only."""

    def __init__(
        self,
        *,
        executor_pool: ExecutorWorkerPool | None = None,
        event_bus: EventBus | None = None,
        config: GitAgentConfig | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.executor_pool = executor_pool or ExecutorWorkerPool(max_workers=1, event_bus=self.event_bus)
        self.config = config or GitAgentConfig()

    async def run(self, request: GitAutonomyRequest) -> GitAutonomyResult:
        self._validate_request(request)
        operations: list[dict[str, Any]] = []
        branch: BranchPlan | None = None
        diff: DiffAnalysis | None = None
        commits: tuple[CommitPlan, ...] = ()
        push_result: dict[str, Any] | None = None

        try:
            branch = self.plan_branch(request)
            branch_operation = await self._run_command(
                request,
                "branch",
                branch.command,
                lock_key=f"git:{request.repo_path}",
            )
            operations.append(branch_operation)
            if not branch_operation["success"]:
                return await self._failed(request, GitStage.FAILED, "branch creation failed", branch, diff, commits, push_result, operations)
            await self._publish(request, GitStage.BRANCH_CREATED, "Feature branch created", {"branch": branch.to_dict()})

            diff_operation = await self._run_tool(
                request,
                "diff",
                "git_diff",
                {"cwd": request.repo_path},
                lock_key=f"git:{request.repo_path}",
            )
            operations.append(diff_operation)
            if not diff_operation["success"]:
                return await self._failed(request, GitStage.FAILED, "diff analysis failed", branch, diff, commits, push_result, operations)
            diff = self.analyze_diff(diff_operation["output"], fallback_paths=request.changed_paths)
            await self._publish(request, GitStage.DIFF_ANALYZED, "Git diff analyzed", {"diff": diff.to_dict()})

            commits = self.plan_commits(request, diff)
            if not commits:
                return await self._failed(request, GitStage.FAILED, "no commit plan generated", branch, diff, commits, push_result, operations)

            for index, commit in enumerate(commits, start=1):
                stage_operation = await self._run_command(
                    request,
                    f"stage-{index:03d}",
                    commit.stage_command,
                    lock_key=f"git:{request.repo_path}",
                )
                operations.append(stage_operation)
                if not stage_operation["success"]:
                    return await self._failed(request, GitStage.FAILED, "staging failed", branch, diff, commits, push_result, operations)

                commit_operation = await self._run_command(
                    request,
                    f"commit-{index:03d}",
                    commit.commit_command,
                    lock_key=f"git:{request.repo_path}",
                )
                operations.append(commit_operation)
                if not commit_operation["success"]:
                    return await self._failed(request, GitStage.FAILED, "commit failed", branch, diff, commits, push_result, operations)
            await self._publish(
                request,
                GitStage.COMMITTED,
                "Atomic commits created",
                {"commits": [commit.to_dict() for commit in commits]},
            )

            if request.push:
                push_command = f"git push -u {shlex.quote(request.remote or self.config.default_remote)} {shlex.quote(branch.name)}"
                push_result = await self._run_command(
                    request,
                    "push",
                    push_command,
                    lock_key=f"git:{request.repo_path}",
                    allow_network=self.config.push_allow_network,
                )
                operations.append(push_result)
                if not push_result["success"]:
                    return await self._failed(request, GitStage.FAILED, "push failed", branch, diff, commits, push_result, operations)
                await self._publish(request, GitStage.PUSHED, "Feature branch pushed", {"push": push_result})

            return GitAutonomyResult(
                task_id=request.task_id,
                success=True,
                stage=GitStage.PUSHED if request.push else GitStage.COMMITTED,
                branch=branch,
                diff=diff,
                commits=commits,
                push_result=push_result,
                operations=tuple(operations),
            )
        except Exception as exc:
            return await self._failed(
                request,
                GitStage.FAILED,
                f"{exc.__class__.__name__}: {exc}",
                branch,
                diff,
                commits,
                push_result,
                operations,
            )

    def run_sync(self, request: GitAutonomyRequest) -> GitAutonomyResult:
        return asyncio.run(self.run(request))

    def plan_branch(self, request: GitAutonomyRequest) -> BranchPlan:
        branch_prefix = (request.branch_prefix or self.config.default_branch_prefix).strip().strip("/")
        branch = f"{branch_prefix}/{_safe_ref(request.task_id)}"
        if request.base_branch:
            command = f"git checkout -B {shlex.quote(branch)} {shlex.quote(request.base_branch)}"
        else:
            command = f"git checkout -B {shlex.quote(branch)}"
        return BranchPlan(name=branch, base_branch=request.base_branch, command=command)

    def analyze_diff(self, output: Any, *, fallback_paths: tuple[str, ...] = ()) -> DiffAnalysis:
        raw = _string_output(output)
        files = []
        additions = 0
        deletions = 0

        for line in raw.splitlines():
            if line.startswith("diff --git "):
                parts = line.split()
                if len(parts) >= 4:
                    files.append(parts[3].removeprefix("b/"))
            elif line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

        changed_files = tuple(dict.fromkeys(files or fallback_paths))
        risk = self._risk(changed_files, additions, deletions, raw)
        summary = f"{len(changed_files)} file(s), +{additions}/-{deletions}, risk={risk}"
        return DiffAnalysis(
            changed_files=changed_files,
            additions=additions,
            deletions=deletions,
            risk=risk,
            summary=summary,
            raw=raw,
        )

    def plan_commits(self, request: GitAutonomyRequest, diff: DiffAnalysis) -> tuple[CommitPlan, ...]:
        specs = request.atomic_commits
        if not specs:
            paths = request.changed_paths or diff.changed_files
            specs = (AtomicCommitSpec(paths=tuple(paths), kind="feat", scope=request.repo_id),)

        return tuple(self._commit_plan(request, spec, index) for index, spec in enumerate(specs, start=1))

    def semantic_commit_message(self, request: GitAutonomyRequest, spec: AtomicCommitSpec, index: int) -> str:
        if spec.message and spec.message.strip():
            return spec.message.strip()
        kind = _safe_commit_type(spec.kind)
        scope = f"({_safe_scope(spec.scope or request.repo_id)})" if (spec.scope or request.repo_id) else ""
        description = re.sub(r"\s+", " ", request.description.strip().splitlines()[0])
        if len(description) > 72:
            description = description[:69].rstrip() + "..."
        return f"{kind}{scope}: {description or f'autonomous task {index}'}"

    async def _run_tool(
        self,
        request: GitAutonomyRequest,
        node_id: str,
        tool: str,
        tool_input: dict[str, Any],
        *,
        lock_key: str,
    ) -> dict[str, Any]:
        node = TaskGraphNode(
            id=f"{request.task_id}:git:{node_id}",
            type=TaskGraphNodeType.EXECUTE,
            payload={
                "task_id": request.task_id,
                "repo_id": request.repo_id,
                "tool": tool,
                "input": tool_input,
                "lock_key": lock_key,
            },
        )
        return self._operation(node_id, tool, tool_input, await self.executor_pool.node_runner(node))

    async def _run_command(
        self,
        request: GitAutonomyRequest,
        node_id: str,
        command: str,
        *,
        lock_key: str,
        allow_network: bool = False,
    ) -> dict[str, Any]:
        return await self._run_tool(
            request,
            node_id,
            "run_command",
            {
                "cmd": command,
                "cwd": request.repo_path,
                "allow_network": allow_network,
            },
            lock_key=lock_key,
        )

    def _operation(self, node_id: str, tool: str, tool_input: dict[str, Any], result: NodeExecutionResult) -> dict[str, Any]:
        return {
            "node_id": node_id,
            "tool": tool,
            "input": dict(tool_input),
            "success": result.success,
            "output": result.output,
            "error": result.error,
        }

    def _commit_plan(self, request: GitAutonomyRequest, spec: AtomicCommitSpec, index: int) -> CommitPlan:
        paths = tuple(path for path in spec.paths if path.strip())
        if paths:
            quoted_paths = " ".join(shlex.quote(path) for path in paths)
            stage_command = f"git add -- {quoted_paths}"
        else:
            stage_command = "git add -A"
        message = self.semantic_commit_message(request, spec, index)
        commit_command = f"git commit -m {shlex.quote(message)}"
        return CommitPlan(
            message=message,
            paths=paths,
            stage_command=stage_command,
            commit_command=commit_command,
        )

    def _risk(self, files: tuple[str, ...], additions: int, deletions: int, raw: str) -> str:
        sensitive = {"pyproject.toml", "package.json", "requirements.txt", "Dockerfile"}
        if any(file in sensitive or file.endswith((".lock", ".sql")) for file in files):
            return "high"
        if additions + deletions > 500 or "delete mode" in raw:
            return "high"
        if additions + deletions > 100 or len(files) > 8:
            return "medium"
        return "low"

    def _validate_request(self, request: GitAutonomyRequest) -> None:
        if not request.task_id.strip():
            raise ValueError("task_id is required")
        if not request.description.strip():
            raise ValueError("description is required")
        if not request.repo_path.strip():
            raise ValueError("repo_path is required")

    async def _failed(
        self,
        request: GitAutonomyRequest,
        stage: GitStage,
        error: str,
        branch: BranchPlan | None,
        diff: DiffAnalysis | None,
        commits: tuple[CommitPlan, ...],
        push_result: dict[str, Any] | None,
        operations: list[dict[str, Any]],
    ) -> GitAutonomyResult:
        await self._publish(request, GitStage.FAILED, error)
        return GitAutonomyResult(
            task_id=request.task_id,
            success=False,
            stage=stage,
            branch=branch,
            diff=diff,
            commits=commits,
            push_result=push_result,
            operations=tuple(operations),
            error=error,
        )

    async def _publish(
        self,
        request: GitAutonomyRequest,
        stage: GitStage,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event_type = EventType.TASK_FAILED if stage == GitStage.FAILED else EventType.TASK_STATE_CHANGED
        event = OrchestrationEvent(
            event_type=event_type,
            task_id=request.task_id,
            message=message,
            payload={
                "stage": stage.value,
                "repo_id": request.repo_id,
                "repo_path": request.repo_path,
                **(payload or {}),
            },
        )
        published = self.event_bus.publish(event)
        if isawaitable(published):
            await published


def _safe_ref(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._/-]+", "-", value.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-/.")
    return normalized[:80] or "task"


def _safe_scope(value: str | None) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", (value or "").strip().lower()).strip("-") or "repo"


def _safe_commit_type(value: str) -> str:
    candidate = re.sub(r"[^a-zA-Z]+", "", value.strip().lower())
    return candidate if candidate in {"feat", "fix", "docs", "test", "refactor", "chore", "ci", "build"} else "feat"


def _string_output(output: Any) -> str:
    if isinstance(output, str):
        return output
    return json.dumps(output, sort_keys=True, default=str)


__all__ = [
    "AtomicCommitSpec",
    "BranchPlan",
    "CommitPlan",
    "DiffAnalysis",
    "GitAgent",
    "GitAgentConfig",
    "GitAutonomyRequest",
    "GitAutonomyResult",
    "GitStage",
]
