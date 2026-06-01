"""Entrypoints for scheduled knowledge maintenance."""

from __future__ import annotations

from typing import Any

from knowledge.service import get_knowledge_service


def run_knowledge_maintenance(apply: bool = True) -> dict[str, Any]:
    return get_knowledge_service().maintain(apply=apply)


__all__ = ["run_knowledge_maintenance"]

