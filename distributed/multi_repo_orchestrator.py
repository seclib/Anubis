"""Multi-repository orchestration for ANUBIS Level 3."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any


class RepoStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DEGRADED = "degraded"


class RepoRole(StrEnum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    SERVICE = "service"
    LIBRARY = "library"
    INFRA = "infra"
    DOCS = "docs"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RepositoryMetadata:
    repo_id: str
    name: str
    path: str
    language: str
    structure: tuple[str, ...] = ()
    status: RepoStatus = RepoStatus.ACTIVE
    role: RepoRole = RepoRole.UNKNOWN
    tags: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "name": self.name,
            "path": self.path,
            "language": self.language,
            "structure": list(self.structure),
            "status": self.status.value,
            "role": self.role.value,
            "tags": list(self.tags),
            "dependencies": list(self.dependencies),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RepoSelection:
    repo: RepositoryMetadata
    score: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo.to_dict(),
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class RepoTaskRoute:
    route_id: str
    repo_id: str
    task_id: str
    goal: str
    depends_on: tuple[str, ...] = ()
    selection_score: int = 0
    selection_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "repo_id": self.repo_id,
            "task_id": self.task_id,
            "goal": self.goal,
            "depends_on": list(self.depends_on),
            "selection_score": self.selection_score,
            "selection_reasons": list(self.selection_reasons),
        }


@dataclass(frozen=True)
class CrossRepoPlan:
    task_id: str
    goal: str
    routes: tuple[RepoTaskRoute, ...]
    cross_repo: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "routes": [route.to_dict() for route in self.routes],
            "cross_repo": self.cross_repo,
        }


class RepoRegistry:
    """Tracks repositories and their routing metadata."""

    def __init__(self, repos: tuple[RepositoryMetadata, ...] | None = None) -> None:
        self._repos: dict[str, RepositoryMetadata] = {}
        for repo in repos or ():
            self.register(repo)

    def register(self, repo: RepositoryMetadata) -> RepositoryMetadata:
        if not repo.repo_id.strip():
            raise ValueError("repo_id is required")
        if not repo.name.strip():
            raise ValueError("repo name is required")
        normalized = replace(
            repo,
            repo_id=repo.repo_id.strip(),
            name=repo.name.strip(),
            path=repo.path.strip(),
            language=repo.language.strip().lower(),
            structure=tuple(item.strip().lower() for item in repo.structure if item.strip()),
            tags=tuple(item.strip().lower() for item in repo.tags if item.strip()),
            dependencies=tuple(item.strip() for item in repo.dependencies if item.strip()),
        )
        self._repos[normalized.repo_id] = normalized
        return normalized

    def get(self, repo_id: str) -> RepositoryMetadata:
        try:
            return self._repos[repo_id]
        except KeyError as exc:
            raise KeyError(f"Unknown repo: {repo_id}") from exc

    def all(self, *, include_disabled: bool = False) -> tuple[RepositoryMetadata, ...]:
        repos = tuple(self._repos[repo_id] for repo_id in sorted(self._repos))
        if include_disabled:
            return repos
        return tuple(repo for repo in repos if repo.status != RepoStatus.DISABLED)

    def update_status(self, repo_id: str, status: RepoStatus | str) -> RepositoryMetadata:
        repo = self.get(repo_id)
        updated = replace(repo, status=RepoStatus(status))
        self._repos[repo_id] = updated
        return updated


class RepoSelector:
    """Selects repositories for a task using deterministic metadata scoring."""

    ROLE_TERMS: dict[RepoRole, frozenset[str]] = {
        RepoRole.FRONTEND: frozenset({"frontend", "ui", "react", "view", "component", "css", "page"}),
        RepoRole.BACKEND: frozenset({"backend", "api", "server", "database", "endpoint", "auth"}),
        RepoRole.SERVICE: frozenset({"service", "worker", "queue", "job", "agent"}),
        RepoRole.LIBRARY: frozenset({"library", "sdk", "package", "shared", "client"}),
        RepoRole.INFRA: frozenset({"infra", "docker", "deploy", "kubernetes", "ci", "redis"}),
        RepoRole.DOCS: frozenset({"docs", "readme", "documentation", "guide"}),
        RepoRole.UNKNOWN: frozenset(),
    }

    def select(
        self,
        task: str,
        registry: RepoRegistry,
        *,
        max_repos: int | None = None,
        min_score: int = 1,
    ) -> tuple[RepoSelection, ...]:
        terms = _terms(task)
        selections = [
            selection
            for repo in registry.all()
            if (selection := self._score_repo(repo, terms)).score >= min_score
        ]
        selections.sort(key=lambda item: (-item.score, item.repo.repo_id))
        if max_repos is not None:
            return tuple(selections[:max_repos])
        return tuple(selections)

    def _score_repo(self, repo: RepositoryMetadata, terms: set[str]) -> RepoSelection:
        score = 0
        reasons: list[str] = []

        for token in _terms(repo.name):
            if token in terms:
                score += 6
                reasons.append(f"name:{token}")
        if repo.language and repo.language in terms:
            score += 5
            reasons.append(f"language:{repo.language}")
        for tag in repo.tags:
            if tag in terms:
                score += 4
                reasons.append(f"tag:{tag}")
        for item in repo.structure:
            item_terms = _terms(item)
            matches = sorted(item_terms & terms)
            if matches:
                score += 3 * len(matches)
                reasons.extend(f"structure:{match}" for match in matches)
        role_matches = sorted(self.ROLE_TERMS.get(repo.role, frozenset()) & terms)
        if role_matches:
            score += 4 * len(role_matches)
            reasons.extend(f"role:{match}" for match in role_matches)
        if repo.status == RepoStatus.DEGRADED:
            score -= 2
            reasons.append("status:degraded")

        return RepoSelection(repo=repo, score=max(score, 0), reasons=tuple(dict.fromkeys(reasons)))


class CrossRepoPlanner:
    """Creates route-level plans across selected repositories."""

    CROSS_REPO_TERMS = frozenset(
        {
            "fullstack",
            "full-stack",
            "end-to-end",
            "integration",
            "api",
            "frontend",
            "backend",
            "service",
            "infra",
            "deploy",
            "client",
        }
    )

    def build(
        self,
        *,
        task_id: str,
        goal: str,
        selections: tuple[RepoSelection, ...],
    ) -> CrossRepoPlan:
        selected = self._order_by_dependencies(self._span_repositories(goal, selections))
        routes: list[RepoTaskRoute] = []
        prior_route_ids: dict[str, str] = {}

        for selection in selected:
            dependencies = tuple(
                route_id
                for dependency in selection.repo.dependencies
                if (route_id := prior_route_ids.get(dependency))
            )
            route_id = f"{task_id}:{selection.repo.repo_id}"
            prior_route_ids[selection.repo.repo_id] = route_id
            routes.append(
                RepoTaskRoute(
                    route_id=route_id,
                    repo_id=selection.repo.repo_id,
                    task_id=task_id,
                    goal=self._repo_goal(goal, selection.repo),
                    depends_on=dependencies,
                    selection_score=selection.score,
                    selection_reasons=selection.reasons,
                )
            )

        return CrossRepoPlan(
            task_id=task_id,
            goal=goal,
            routes=tuple(routes),
            cross_repo=len(routes) > 1,
        )

    def _span_repositories(self, goal: str, selections: tuple[RepoSelection, ...]) -> tuple[RepoSelection, ...]:
        if not selections:
            return ()
        terms = _terms(goal)
        if len(selections) == 1:
            return selections
        role_count = len({selection.repo.role for selection in selections if selection.repo.role != RepoRole.UNKNOWN})
        explicit_cross_repo = bool(terms & self.CROSS_REPO_TERMS)
        if explicit_cross_repo or role_count > 1:
            return selections
        return selections[:1]

    def _order_by_dependencies(self, selections: tuple[RepoSelection, ...]) -> tuple[RepoSelection, ...]:
        by_repo_id = {selection.repo.repo_id: selection for selection in selections}
        ordered: list[RepoSelection] = []
        ordered_ids: set[str] = set()
        remaining = dict(by_repo_id)

        while remaining:
            ready = [
                repo_id
                for repo_id, selection in remaining.items()
                if all(dependency not in by_repo_id or dependency in ordered_ids for dependency in selection.repo.dependencies)
            ]
            if not ready:
                ready = sorted(remaining)
            for repo_id in sorted(ready):
                selection = remaining.pop(repo_id)
                ordered.append(selection)
                ordered_ids.add(repo_id)

        return tuple(ordered)

    def _repo_goal(self, goal: str, repo: RepositoryMetadata) -> str:
        return f"[{repo.name}] {goal}"


class MultiRepoOrchestrator:
    """Coordinates repository selection and cross-repo task routing."""

    def __init__(
        self,
        *,
        registry: RepoRegistry | None = None,
        selector: RepoSelector | None = None,
        planner: CrossRepoPlanner | None = None,
    ) -> None:
        self.registry = registry or RepoRegistry()
        self.selector = selector or RepoSelector()
        self.planner = planner or CrossRepoPlanner()

    def register_repo(self, repo: RepositoryMetadata) -> RepositoryMetadata:
        return self.registry.register(repo)

    def select_repos(self, task: str, *, max_repos: int | None = None) -> tuple[RepoSelection, ...]:
        selections = self.selector.select(task, self.registry, max_repos=max_repos)
        if selections:
            return selections
        active = self.registry.all()
        if not active:
            return ()
        fallback = active[0]
        return (
            RepoSelection(
                repo=fallback,
                score=0,
                reasons=("fallback:first-active-repo",),
            ),
        )

    def plan_task(
        self,
        *,
        task_id: str,
        goal: str,
        max_repos: int | None = None,
    ) -> CrossRepoPlan:
        selections = self.select_repos(goal, max_repos=max_repos)
        return self.planner.build(task_id=task_id, goal=goal, selections=selections)

    def route_task(
        self,
        *,
        task_id: str,
        goal: str,
        max_repos: int | None = None,
    ) -> tuple[RepoTaskRoute, ...]:
        return self.plan_task(task_id=task_id, goal=goal, max_repos=max_repos).routes


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9_-]*", text.lower()))


__all__ = [
    "CrossRepoPlan",
    "CrossRepoPlanner",
    "MultiRepoOrchestrator",
    "RepoRegistry",
    "RepoRole",
    "RepoSelection",
    "RepoSelector",
    "RepoStatus",
    "RepoTaskRoute",
    "RepositoryMetadata",
]
