from __future__ import annotations

import atexit
import readline
from pathlib import Path

from config import OLLAMA_MODEL, PROJECT_ROOT
from cli.theme import compact_path
from cli.ui import console

HISTORY_FILE = Path.home() / ".anubis_history"
MAX_HISTORY = 2000


def setup_readline() -> None:
    readline.set_history_length(MAX_HISTORY)
    readline.parse_and_bind("tab: complete")
    readline.parse_and_bind("set editing-mode emacs")
    if HISTORY_FILE.exists():
        try:
            readline.read_history_file(str(HISTORY_FILE))
        except OSError:
            pass
    atexit.register(save_history)


def save_history() -> None:
    try:
        readline.write_history_file(str(HISTORY_FILE))
    except OSError:
        pass


def read_input() -> str | None:
    try:
        cwd = compact_path(PROJECT_ROOT, 26)
        model = OLLAMA_MODEL.replace("qwen2.5-coder:", "qwen ")
        prompt = (
            "\033[38;5;242m>\033[0m "
            "\033[48;2;217;119;87m\033[38;5;16m anubis \033[0m"
            f"\033[48;5;235m\033[38;5;250m {cwd} \033[0m"
            f"\033[48;5;236m\033[38;2;217;119;87m {model} \033[0m "
        )
        line = input(prompt).strip()
    except EOFError:
        return None
    except KeyboardInterrupt:
        console.print()
        return ""

    if not line:
        return ""

    if line == "```" or line.startswith("```"):
        lines = [line]
        while True:
            try:
                continuation = input("... ")
                lines.append(continuation)
                if continuation.strip() == "```":
                    break
            except (EOFError, KeyboardInterrupt):
                break
        return "\n".join(lines)

    return line

