from __future__ import annotations

from pathlib import Path
from typing import Any

from anubis.context.builder import ContextBuilder
from anubis.context.schema import ContextBudget, ContextBuildRequest, MinimalContext, RepositoryIndex


class ContextBuilderService:
    """Service boundary for creating minimal LLM context payloads."""

    def __init__(self, root: Path | str, builder: ContextBuilder | None = None) -> None:
        self.builder = builder or ContextBuilder(root)

    def build_context(
        self,
        task: str,
        *,
        repo_state: dict[str, Any] | None = None,
        memory: dict[str, Any] | None = None,
        budget: ContextBudget | None = None,
        index: RepositoryIndex | None = None,
    ) -> MinimalContext:
        request = ContextBuildRequest(
            task=task,
            repo_state=dict(repo_state or {}),
            memory=dict(memory or {}),
            budget=budget or ContextBudget(),
        )
        return self.builder.build_minimal(request, index=index)


__all__ = ["ContextBuilderService"]
