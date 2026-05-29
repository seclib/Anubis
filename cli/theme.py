from __future__ import annotations

import json
import sys
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.text import Text

from config import OLLAMA_BASE_URL, OLLAMA_MODEL, PROJECT_ROOT, STATE_DIR
from cli.ui import CLAUDE_ORANGE, MUTED_TEXT, VERSION, console
from runtime.tool_registry import tool_registry

def compact_path(path: Path, max_len: int = 48) -> str:
    text = str(path)
    if len(text) <= max_len:
        return text
    return "..." + text[-(max_len - 3):]


def _visible_width(text: str) -> int:
    return len(text.rstrip())


def _fit(text: str, width: int) -> str:
    clean = text.rstrip()
    if len(clean) <= width:
        return clean
    if width <= 1:
        return clean[:width]
    return clean[: width - 1] + "…"


def _center(text: str, width: int) -> str:
    return _fit(text, width).center(width)


def recent_activity() -> str:
    session_file = STATE_DIR / "cli_session.jsonl"
    if not session_file.exists():
        return "No recent activity"
    try:
        lines = session_file.read_text(encoding="utf-8").splitlines()[-20:]
        for raw in reversed(lines):
            event = json.loads(raw)
            if event.get("role") == "user":
                content = str(event.get("content", "")).replace("\n", " ").strip()
                return content[:42] or "No recent activity"
    except Exception:
        return "Recent activity unavailable"
    return "No recent activity"


def banner_panel() -> Panel:
    left_width = 34
    max_content_width = min(max(console.width - 8, 70), 88)
    right_width = max(32, max_content_width - left_width - 3)

    left_lines = [
        ("Welcome back.", "bold white"),
        ("", MUTED_TEXT),
        (_fit("local autonomous dev agent", left_width), MUTED_TEXT),
        (_fit("Hermes-style CLI runtime", left_width), MUTED_TEXT),
        ("", MUTED_TEXT),
        (_fit(f"model   {OLLAMA_MODEL}", left_width), MUTED_TEXT),
        (_fit(f"tools   {len(tool_registry())} loaded", left_width), MUTED_TEXT),
        (_fit(f"scope   ~{compact_path(PROJECT_ROOT, left_width - 9)}", left_width), MUTED_TEXT),
    ]
    right_lines = [
        ("Tips for getting started", f"bold {CLAUDE_ORANGE}"),
        (_fit("Ask Anubis to inspect, edit, test,", right_width), "white"),
        (_fit("or refactor this repo", right_width), "white"),
        ("-" * right_width, CLAUDE_ORANGE),
        ("Recent activity", f"bold {CLAUDE_ORANGE}"),
        (recent_activity()[:right_width], MUTED_TEXT),
        ("Shortcuts", f"bold {CLAUDE_ORANGE}"),
        (_fit("/help · /model · /tools", right_width), MUTED_TEXT),
        (_fit("/run <task> · /exit", right_width), MUTED_TEXT),
        (_fit(f"endpoint: {OLLAMA_BASE_URL}", right_width), MUTED_TEXT),
    ]

    height = max(len(left_lines), len(right_lines))
    left_lines.extend([("", "bright_black")] * (height - len(left_lines)))
    right_lines.extend([("", "bright_black")] * (height - len(right_lines)))

    layout = Text()
    for index, ((left, left_style), (right, right_style)) in enumerate(zip(left_lines, right_lines)):
        layout.append(f"{_fit(left, left_width):<{left_width}}", style=left_style)
        layout.append("│", style=CLAUDE_ORANGE)
        layout.append(f" {_fit(right, right_width):<{right_width}}", style=right_style)
        if index < height - 1:
            layout.append("\n")

    return Panel(
        layout,
        title=f"[bold {CLAUDE_ORANGE}] Anubis Code [/][{MUTED_TEXT}]v{VERSION}[/]",
        title_align="left",
        border_style=CLAUDE_ORANGE,
        box=box.ROUNDED,
        expand=False,
        padding=(0, 1),
    )


def print_banner() -> None:
    console.clear()
    sys.stdout.write(f"\033]0;Anubis Code - {OLLAMA_MODEL}\007")
    sys.stdout.flush()
    console.print(banner_panel())
    console.print(f"[{MUTED_TEXT}]/model[/] to inspect the active Ollama model\n")
