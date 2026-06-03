"""Native Git workspace service for ANUBIS desktop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
import subprocess
from typing import Any


class GitWorkspaceError(RuntimeError):
    """Raised when a git workspace operation cannot be completed."""


@dataclass(frozen=True)
class GitCommandResult:
    command: tuple[str, ...]
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "code": self.code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "ok": self.ok,
        }


@dataclass(frozen=True)
class GitFileChange:
    path: str
    status: str
    staged: bool = False
    unstaged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GitWorkspaceStatus:
    repo_path: str
    branch: str
    upstream: str | None
    clean: bool
    changes: tuple[GitFileChange, ...]
    ahead: int = 0
    behind: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "branch": self.branch,
            "upstream": self.upstream,
            "clean": self.clean,
            "changes": [change.to_dict() for change in self.changes],
            "ahead": self.ahead,
            "behind": self.behind,
        }


@dataclass(frozen=True)
class DiffFile:
    path: str
    status: str
    additions: int = 0
    deletions: int = 0
    hunks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status,
            "additions": self.additions,
            "deletions": self.deletions,
            "hunks": list(self.hunks),
        }


@dataclass(frozen=True)
class DiffView:
    repo_path: str
    files: tuple[DiffFile, ...]
    raw: str
    additions: int = 0
    deletions: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "files": [file.to_dict() for file in self.files],
            "raw": self.raw,
            "additions": self.additions,
            "deletions": self.deletions,
        }


@dataclass(frozen=True)
class BranchCreationResult:
    branch: str
    base_branch: str | None
    command: GitCommandResult

    @property
    def success(self) -> bool:
        return self.command.ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "base_branch": self.base_branch,
            "success": self.success,
            "command": self.command.to_dict(),
        }


@dataclass(frozen=True)
class CommitProposal:
    message: str
    paths: tuple[str, ...]
    summary: str
    risk: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "paths": list(self.paths),
            "summary": self.summary,
            "risk": self.risk,
        }


@dataclass(frozen=True)
class CommitResult:
    proposal: CommitProposal
    stage: GitCommandResult
    commit: GitCommandResult
    commit_sha: str | None = None

    @property
    def success(self) -> bool:
        return self.stage.ok and self.commit.ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "proposal": self.proposal.to_dict(),
            "stage": self.stage.to_dict(),
            "commit": self.commit.to_dict(),
            "commit_sha": self.commit_sha,
        }


@dataclass(frozen=True)
class PullRequestDraft:
    title: str
    body: str
    head_branch: str
    base_branch: str
    changed_files: tuple[str, ...]
    diff_summary: str
    risks: tuple[str, ...] = ()
    linked_tasks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "head_branch": self.head_branch,
            "base_branch": self.base_branch,
            "changed_files": list(self.changed_files),
            "diff_summary": self.diff_summary,
            "risks": list(self.risks),
            "linked_tasks": list(self.linked_tasks),
        }


@dataclass(frozen=True)
class GitWorkspaceConfig:
    root: Path = Path(".")
    timeout_seconds: float = 10.0


class GitWorkspace:
    """First-class Git operations for desktop workspace UX."""

    def __init__(self, repo_path: str | Path = ".", *, config: GitWorkspaceConfig | None = None) -> None:
        self.config = config or GitWorkspaceConfig()
        self.repo_path = self._resolve_repo(repo_path)

    def status(self) -> GitWorkspaceStatus:
        branch_result = self._git("branch", "--show-current")
        branch = branch_result.stdout.strip() or "HEAD"
        upstream_result = self._git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
        upstream = upstream_result.stdout.strip() if upstream_result.ok else None
        ahead = behind = 0
        if upstream:
            counts = self._git("rev-list", "--left-right", "--count", f"{branch}...{upstream}", check=False)
            if counts.ok:
                parts = counts.stdout.strip().split()
                if len(parts) == 2:
                    ahead, behind = int(parts[0]), int(parts[1])
        porcelain = self._git("status", "--porcelain=v1")
        changes = tuple(_parse_status(porcelain.stdout))
        return GitWorkspaceStatus(
            repo_path=str(self.repo_path),
            branch=branch,
            upstream=upstream,
            clean=not changes,
            changes=changes,
            ahead=ahead,
            behind=behind,
        )

    def create_branch(self, branch: str, *, base_branch: str | None = None) -> BranchCreationResult:
        safe_branch = _safe_branch(branch)
        args = ["checkout", "-B", safe_branch]
        if base_branch:
            args.append(base_branch)
        result = self._git(*args, check=False)
        return BranchCreationResult(branch=safe_branch, base_branch=base_branch, command=result)

    def diff(self, *, paths: tuple[str, ...] = (), staged: bool = False) -> DiffView:
        args = ["diff", "--no-ext-diff"]
        if staged:
            args.append("--cached")
        args.extend(["--", *paths])
        raw = self._git(*args).stdout
        return _parse_diff(raw, repo_path=str(self.repo_path))

    def generate_commit(self, *, description: str, paths: tuple[str, ...] = (), kind: str = "feat", scope: str | None = None) -> CommitProposal:
        diff = self.diff(paths=paths)
        selected_paths = paths or tuple(file.path for file in diff.files) or tuple(change.path for change in self.status().changes)
        message = _semantic_message(kind=kind, scope=scope, description=description)
        risk = _diff_risk(diff)
        summary = f"{len(selected_paths)} file(s), +{diff.additions}/-{diff.deletions}, risk={risk}"
        return CommitProposal(message=message, paths=selected_paths, summary=summary, risk=risk)

    def commit(self, proposal: CommitProposal) -> CommitResult:
        paths = proposal.paths
        stage_args = ["add", "--", *paths] if paths else ["add", "-A"]
        stage = self._git(*stage_args, check=False)
        if not stage.ok:
            return CommitResult(proposal=proposal, stage=stage, commit=GitCommandResult(("git", "commit"), 1, "", "staging failed"))
        commit = self._git("commit", "-m", proposal.message, check=False)
        sha = None
        if commit.ok:
            sha_result = self._git("rev-parse", "--short", "HEAD", check=False)
            sha = sha_result.stdout.strip() if sha_result.ok else None
        return CommitResult(proposal=proposal, stage=stage, commit=commit, commit_sha=sha)

    def prepare_pr(
        self,
        *,
        title: str | None = None,
        description: str = "",
        base_branch: str = "main",
        linked_tasks: tuple[str, ...] = (),
    ) -> PullRequestDraft:
        status = self.status()
        diff = self.diff()
        changed_files = tuple(file.path for file in diff.files) or tuple(change.path for change in status.changes)
        pr_title = title or _title_from_description(description, status.branch)
        risks = _pr_risks(diff, status)
        body = _pr_body(description=description, diff=diff, risks=risks, linked_tasks=linked_tasks)
        return PullRequestDraft(
            title=pr_title,
            body=body,
            head_branch=status.branch,
            base_branch=base_branch,
            changed_files=changed_files,
            diff_summary=f"{len(changed_files)} file(s), +{diff.additions}/-{diff.deletions}",
            risks=risks,
            linked_tasks=linked_tasks,
        )

    def _git(self, *args: str, check: bool = True) -> GitCommandResult:
        command = ("git", *args)
        completed = subprocess.run(
            command,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=self.config.timeout_seconds,
            check=False,
        )
        result = GitCommandResult(command=command, code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
        if check and not result.ok:
            raise GitWorkspaceError(result.stderr.strip() or result.stdout.strip() or f"git command failed: {' '.join(command)}")
        return result

    def _resolve_repo(self, repo_path: str | Path) -> Path:
        root = self.config.root.resolve(strict=False)
        candidate = Path(repo_path)
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve(strict=False)
        git_dir = resolved / ".git"
        if not git_dir.exists():
            raise GitWorkspaceError(f"not a git repository: {resolved}")
        return resolved


def _parse_status(raw: str) -> list[GitFileChange]:
    changes: list[GitFileChange] = []
    for line in raw.splitlines():
        if not line:
            continue
        index_status = line[0]
        worktree_status = line[1] if len(line) > 1 else " "
        path = line[3:] if len(line) > 3 else line[2:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        status = _status_label(index_status, worktree_status)
        changes.append(
            GitFileChange(
                path=path,
                status=status,
                staged=index_status not in {" ", "?"},
                unstaged=worktree_status not in {" "},
            )
        )
    return changes


def _parse_diff(raw: str, *, repo_path: str) -> DiffView:
    files: list[DiffFile] = []
    current_path = ""
    current_status = "modified"
    current_hunks: list[str] = []
    current_additions = 0
    current_deletions = 0
    total_additions = 0
    total_deletions = 0

    def flush() -> None:
        nonlocal current_path, current_status, current_hunks, current_additions, current_deletions
        if current_path:
            files.append(
                DiffFile(
                    path=current_path,
                    status=current_status,
                    additions=current_additions,
                    deletions=current_deletions,
                    hunks=tuple(current_hunks),
                )
            )
        current_path = ""
        current_status = "modified"
        current_hunks = []
        current_additions = 0
        current_deletions = 0

    for line in raw.splitlines():
        if line.startswith("diff --git "):
            flush()
            parts = line.split()
            current_path = parts[3].removeprefix("b/") if len(parts) >= 4 else ""
            continue
        if line.startswith("new file mode"):
            current_status = "added"
        elif line.startswith("deleted file mode"):
            current_status = "deleted"
        elif line.startswith("rename to "):
            current_status = "renamed"
            current_path = line.removeprefix("rename to ").strip()
        elif line.startswith("@@"):
            current_hunks.append(line)
        elif line.startswith("+") and not line.startswith("+++"):
            current_additions += 1
            total_additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_deletions += 1
            total_deletions += 1
    flush()
    return DiffView(repo_path=repo_path, files=tuple(files), raw=raw, additions=total_additions, deletions=total_deletions)


def _status_label(index_status: str, worktree_status: str) -> str:
    status = index_status if index_status not in {" ", "?"} else worktree_status
    return {
        "A": "added",
        "M": "modified",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
        "U": "conflicted",
        "?": "untracked",
    }.get(status, "modified")


def _safe_branch(branch: str) -> str:
    value = branch.strip().replace(" ", "-").lower()
    value = re.sub(r"[^a-z0-9._/-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-/.")
    if not value or value.startswith("-") or ".." in value or value.endswith(".lock"):
        raise GitWorkspaceError(f"invalid branch name: {branch}")
    return value


def _semantic_message(*, kind: str, scope: str | None, description: str) -> str:
    safe_kind = re.sub(r"[^a-z]+", "", kind.lower()) or "chore"
    safe_scope = re.sub(r"[^a-z0-9_.-]+", "-", scope.lower()).strip("-") if scope else ""
    subject = re.sub(r"\s+", " ", description.strip().splitlines()[0] if description.strip() else "update workspace")
    subject = subject[:72].rstrip()
    prefix = f"{safe_kind}({safe_scope})" if safe_scope else safe_kind
    return f"{prefix}: {subject}"


def _title_from_description(description: str, branch: str) -> str:
    first = re.sub(r"\s+", " ", description.strip().splitlines()[0]) if description.strip() else ""
    return first[:88].rstrip() or f"Update {branch}"


def _diff_risk(diff: DiffView) -> str:
    sensitive = {"package.json", "pyproject.toml", "requirements.txt", "Dockerfile"}
    if any(file.path in sensitive or file.path.endswith((".lock", ".sql")) for file in diff.files):
        return "high"
    if diff.additions + diff.deletions > 500 or any(file.status == "deleted" for file in diff.files):
        return "high"
    if diff.additions + diff.deletions > 100 or len(diff.files) > 8:
        return "medium"
    return "low"


def _pr_risks(diff: DiffView, status: GitWorkspaceStatus) -> tuple[str, ...]:
    risks: list[str] = []
    risk = _diff_risk(diff)
    if risk != "low":
        risks.append(f"{risk} diff risk")
    if status.behind:
        risks.append(f"branch is {status.behind} commit(s) behind upstream")
    if not diff.files and status.changes:
        risks.append("untracked or staged-only changes may need review")
    return tuple(risks)


def _pr_body(*, description: str, diff: DiffView, risks: tuple[str, ...], linked_tasks: tuple[str, ...]) -> str:
    files = "\n".join(f"- `{file.path}` (+{file.additions}/-{file.deletions})" for file in diff.files) or "- No unstaged diff files"
    risk_lines = "\n".join(f"- {risk}" for risk in risks) or "- Low risk based on diff size and files"
    task_lines = "\n".join(f"- {task}" for task in linked_tasks) or "- None"
    return (
        "## Summary\n\n"
        f"{description.strip() or 'Prepared by ANUBIS native Git workspace.'}\n\n"
        "## Files Changed\n\n"
        f"{files}\n\n"
        "## Risks\n\n"
        f"{risk_lines}\n\n"
        "## Linked Tasks\n\n"
        f"{task_lines}\n"
    )


__all__ = [
    "BranchCreationResult",
    "CommitProposal",
    "CommitResult",
    "DiffFile",
    "DiffView",
    "GitCommandResult",
    "GitFileChange",
    "GitWorkspace",
    "GitWorkspaceConfig",
    "GitWorkspaceError",
    "GitWorkspaceStatus",
    "PullRequestDraft",
]
