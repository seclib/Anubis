from __future__ import annotations

from collections.abc import Mapping

from cli.agents import STATE_ORDER


def render_block(task: str, status: Mapping[str, str] | str | None, result: str) -> str:
    return "\n".join(
        [
            "TASK:",
            clean(task),
            "",
            "STATUS:",
            render_status(status),
            "",
            "RESULT:",
            clean(result),
            "",
            "",
        ]
    )


def render_status(status: Mapping[str, str] | str | None) -> str:
    if status is None:
        return "none"
    if isinstance(status, str):
        return clean(status)
    if not status:
        return "none"

    emitted: set[str] = set()
    lines: list[str] = []
    for name in STATE_ORDER:
        if name in status:
            lines.append(f"- {name}: {status[name]}")
            emitted.add(name)
    for name in sorted(set(status) - emitted):
        lines.append(f"- {name}: {status[name]}")
    return "\n".join(lines)


def clean(text: object) -> str:
    value = str(text).strip()
    return value if value else "none"


__all__ = ["clean", "render_block", "render_status"]
