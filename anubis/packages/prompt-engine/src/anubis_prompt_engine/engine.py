from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PromptSection:
    title: str
    content: str


class PromptEngine:
    """Composes deterministic, inspectable prompts from bounded sections."""

    def compose(self, *, system: str, sections: Iterable[PromptSection], user_message: str) -> str:
        rendered = [f"SYSTEM\n{system.strip()}"]
        for section in sections:
            content = section.content.strip()
            if content:
                rendered.append(f"{section.title.upper()}\n{content}")
        rendered.append(f"USER\n{user_message.strip()}")
        return "\n\n".join(rendered)
