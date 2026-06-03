from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from anubis.workspace import CommitProposal, GitWorkspace, GitWorkspaceConfig, GitWorkspaceError
from backend.core.config import settings


router = APIRouter()


class RepoRequest(BaseModel):
    repo_path: str = "."


class CreateBranchRequest(RepoRequest):
    branch: str = Field(min_length=1)
    base_branch: str | None = None


class DiffRequest(RepoRequest):
    paths: list[str] = Field(default_factory=list)
    staged: bool = False


class GenerateCommitRequest(RepoRequest):
    description: str = Field(min_length=1)
    paths: list[str] = Field(default_factory=list)
    kind: str = "feat"
    scope: str | None = None


class CommitRequest(RepoRequest):
    message: str = Field(min_length=1)
    paths: list[str] = Field(default_factory=list)
    summary: str = ""
    risk: str = "unknown"


class PreparePRRequest(RepoRequest):
    title: str | None = None
    description: str = ""
    base_branch: str = "main"
    linked_tasks: list[str] = Field(default_factory=list)


def workspace(repo_path: str) -> GitWorkspace:
    try:
        return GitWorkspace(
            repo_path,
            config=GitWorkspaceConfig(root=Path(settings.project_root), timeout_seconds=settings.tool_timeout_seconds),
        )
    except GitWorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/status")
def status(payload: RepoRequest) -> dict[str, object]:
    return workspace(payload.repo_path).status().to_dict()


@router.post("/branches")
def create_branch(payload: CreateBranchRequest) -> dict[str, object]:
    return workspace(payload.repo_path).create_branch(payload.branch, base_branch=payload.base_branch).to_dict()


@router.post("/diff")
def diff(payload: DiffRequest) -> dict[str, object]:
    return workspace(payload.repo_path).diff(paths=tuple(payload.paths), staged=payload.staged).to_dict()


@router.post("/commits/proposal")
def generate_commit(payload: GenerateCommitRequest) -> dict[str, object]:
    return workspace(payload.repo_path).generate_commit(
        description=payload.description,
        paths=tuple(payload.paths),
        kind=payload.kind,
        scope=payload.scope,
    ).to_dict()


@router.post("/commits")
def commit(payload: CommitRequest) -> dict[str, object]:
    proposal = CommitProposal(
        message=payload.message,
        paths=tuple(payload.paths),
        summary=payload.summary,
        risk=payload.risk,
    )
    return workspace(payload.repo_path).commit(proposal).to_dict()


@router.post("/pull-request/draft")
def prepare_pr(payload: PreparePRRequest) -> dict[str, object]:
    return workspace(payload.repo_path).prepare_pr(
        title=payload.title,
        description=payload.description,
        base_branch=payload.base_branch,
        linked_tasks=tuple(payload.linked_tasks),
    ).to_dict()
