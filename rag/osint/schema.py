from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rag.shared.utils import stable_id


@dataclass(frozen=True)
class RagDocument:
    domain: str
    title: str
    body: str
    source_uri: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def doc_id(self) -> str:
        return stable_id(self.domain, self.source_uri or self.title)


__all__ = ["RagDocument"]
