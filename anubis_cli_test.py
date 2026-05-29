#!/usr/bin/env python3
"""
Anubis CLI v6 — Hermes Hacker Terminal
Full-featured REPL with intent routing, agent loop, session persistence,
multi-line input, and rich streaming.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import readline
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Tuple

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# Project root on path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    PROJECT_ROOT,
    STATE_DIR,
    CONTINUOUS_RUN,
    MAX_STEPS,
)
from llm.ollama import stream_chat, call_chat
from executor.tool_executor import execute_tool, TOOLS
from memory.state import load_memory, save_memory, get_context_summary, get_task_state_summary
from agent.prompts import SYSTEM_PROMPT

# ── Setup ───────────────────────────────────────────────────────────────
console = Console()
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(STATE_DIR / "cli.log", encoding="utf-8")],
)
logger = logging.getLogger("anubis.cli")

HISTORY_FILE = Path.home() / ".anubis_history"
MAX_HISTORY = 2000
MAX_CONTEXT_MESSAGES = 40
VERSION = "6.0.0"

CLI_SYSTEM_PROMPT = f"""{SYSTEM_PROMPT}

ADDITIONAL CLI RULES:
- You are in interactive terminal mode. Be concise and technical.
- When the user asks a direct question, answer it with Markdown.
- For tool execution, output the standard JSON action block.
- Current working directory: {PROJECT_ROOT}
- Current date: {{date}}
""".strip()


# ── Readline ─────────────────────────────────────────────────────────────
def _setup_readline() -> None:
    readline.set_history_length(MAX_HISTORY)
    readline.parse_and_bind("tab: complete")
    readline.parse_and_bind("set editing-mode emacs")
    if HISTORY_FILE.exists():
        try:
            readline.read_history_file(str(HISTORY_FILE))
        except OSError:
            pass
    atexit.register(_save_history)


def _save_history() -> None:
    try:
        readline.write_history_file(str(HISTORY_FILE))
    except OSError:
        pass


# ── Conversation Memory (Pair-Preserving Sliding Window) ────────────────
class ConversationMemory:
    """Multi-turn context with pair-preserving trim and session logging."""

    def __init__(self, system_prompt: str, session_file: Path | None = None):
        self._system_msg = {"role": "system", "content": system_prompt}
        self._messages: list[dict[str, str]] = [self._system_msg]
        self._background_facts: list[str] = []
        self._total_user_turns = 0
        self._session_file = session_file or (STATE_DIR / "cli_session.jsonl")

    @property
    def messages(self) -> list[dict[str, str]]:
        result = list(self._messages)
        if self._background_facts:
            ctx = "[BACKGROUND CONTEXT — silent tool results]\n" + "\n".join(
                f"• {f}" for f in self._background_facts[-8:]
            )
            result.insert(1, {"role": "system", "content": ctx})
        return result

    @property
    def turn_count(self) -> int:
        return self._total_user_turns

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def add_user(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})
        self._total_user_turns += 1
        self._trim()
        self._log("user", content)

    def add_assistant(self, content: str) -> None:
        self._messages.append({"role": "assistant", "content": content})
        self._trim()
        self._log("assistant", content)

    def inject_context(self, context: str) -> None:
        """Inject ephemeral runtime context (replaced on every call)."""
        self._messages = [
            m for m in self._messages
            if not (m["role"] == "system" and m is not self._system_msg)
        ]
        self._messages.insert(1, {"role": "system", "content": context})

    def inject_fact(self, fact: str) -> None:
        """Silent background fact for tool result injection."""
        self._background_facts.append(fact)
        if len(self._background_facts) > 20:
            self._background_facts = self._background_facts[-20:]

    def clear(self) -> None:
        self._messages = [self._system_msg]
        self._background_facts.clear()

    def get_turns_display(self) -> list[dict]:
        return [
            {"i": i, "role": m["role"], "preview": m["content"][:100].replace("\n", " ")}
            for i, m in enumerate(self._messages)
        ]

    def _trim(self) -> None:
        non_system = [m for m in self._messages if m["role"] != "system"]
        system_msgs = [m for m in self._messages if m["role"] == "system"]
        if len(non_system) > MAX_CONTEXT_MESSAGES:
            excess = len(non_system) - MAX_CONTEXT_MESSAGES
            if excess % 2 != 0:
                excess += 1
            non_system = non_system[excess:]
        self._messages = system_msgs + non_system

    def _log(self, role: str, content: str) -> None:
        entry = {
            "role": role,
            "content": content[:2000],
            "turn": self._total_user_turns,
            "ts": datetime.now().isoformat(),
        }
        try:
            self._session_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._session_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass


# ── Intent Parser (Natural Commands) ────────────────────────────────────
INTENT_MAP = [
    (r"^(scan|nmap)\s+(ports?\s+|network\s+)?(?P<target>\S+)", "run_command", lambda m: {"cmd": f"nmap -F {m['target']}"}),
    (r"^(analyze|lint|audit)\s+(?P<file>\S+)", "run_command", lambda m: {"cmd": f"ruff check {m['file']} 2>/dev/null || python3 -m py_compile {m['file']}"}),
    (r"^(read|cat|show)\s+(?P<path>\S+)", "read_file", lambda m: {"path": m["path"]}),
    (r"^(find|search|grep)\s+(?P<query>.+)", "search_code", lambda m: {"query": m["query"]}),
    (r"^(tree|ls)\s*(?P<path>\S*)", "get_file_tree", lambda m: {"path": m.get("path") or "."}),
    (r"^(status|state)\s*$", "_status", None),
    (r"^(docker)\s+(ps|status)", "run_command", lambda m: {"cmd": "docker ps --format 'table {{.Names}}\\t{{.Status}}'"}),
    (r"^(memory|remember)\s+(?P<fact>.+)", "store_hermes_memory", lambda m: {"summary": m["fact"]}),
    (r"^(git)\s+(?P<sub>status|log|diff)", "run_command", lambda m: {"cmd": f"git {m['sub']}" + (" -n 10 --oneline" if m['sub'] == 'log' else "")}),
]


def parse_intent(user_input: str) -> Tuple[str, dict] | None:
    for pattern, action, args_fn in INTENT_MAP:
        match = re.match(pattern, user_input, re.IGNORECASE)
        if match:
            args = args_fn(match.groupdict()) if args_fn else {}
            return action, args
    return None


# ── Streaming Renderer ──────────────────────────────────────────────────
def stream_response(conversation: ConversationMemory, user_input: str) -> str:
    """Stream LLM response with live Markdown rendering. Returns full text."""
    conversation.add_user(user_input)

    # Inject agent memory context
    try:
        memory = load_memory()
        ctx = get_context_summary(memory)
        if ctx.strip():
            conversation.inject_context(f"[AGENT STATE]\n{ctx}")
    except Exception:
        pass

    full_response = ""
    token_count = 0
    start = time.monotonic()

    console.print()
    with Live(Markdown("▌"), console=console, refresh_per_second=12, transient=False) as live:
        try:
            for token in stream_chat(conversation.messages, model=OLLAMA_MODEL):
                full_response += token
                token_count += 1
                live.update(Markdown(full_response + "▌"))
        except KeyboardInterrupt:
            full_response += "\n\n*(interrupted)*"
            live.update(Markdown(full_response))

    elapsed = time.monotonic() - start
    tps = token_count / elapsed if elapsed > 0 else 0

    console.print(Text(
        f"  {token_count} tokens · {elapsed:.1f}s · {tps:.1f} t/s",
        style="dim"
    ))
    console.print()

    conversation.add_assistant(full_response)
    return full_response


# ── Tool Execution with Visual Feedback ──────────────────────────────────
def execute_and_display(
    action: str,
    args: dict,
    conversation: ConversationMemory,
    user_input: str,
) -> None:
    """Execute a tool, display result in a panel, inject into memory."""
    console.print(f"  [bold magenta]► EXEC[/bold magenta] [cyan]{action}[/cyan] ", end="")
    console.print(f"[dim]{json.dumps(args, ensure_ascii=False)}[/dim]")

    result = execute_tool(action, args)
    success = result.get("success", False)
    output = result.get("output", "")

    # Normalize output
    if isinstance(output, dict):
        out_str = output.get("stdout", "") or output.get("stderr", "") or str(output)
    else:
        out_str = str(output)

    # Truncate for display
    display = out_str[:4000] + ("\n…[TRUNCATED]" if len(out_str) > 4000 else "")

    border = "green" if success else "red"
    icon = "✓" if success else "✗"
    console.print(Panel(
        display.strip() or "(empty output)",
        title=f"[bold]{icon} {action.upper()}[/bold]",
        border_style=border,
        padding=(0, 1),
    ))

    # Inject result silently into LLM background context
    fact = f"[{action}] {user_input} → {'OK' if success else 'FAIL'}: {out_str[:500]}"
    conversation.inject_fact(fact)


# ── Slash Commands ───────────────────────────────────────────────────────
def handle_command(cmd: str, conversation: ConversationMemory) -> bool:
    """Handle slash commands. Returns False to exit."""
    parts = cmd.strip().split(None, 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command in ("/quit", "/exit", "/q"):
        return False

    if command == "/help":
        table = Table(title="Commands", border_style="dim", show_header=False)
        table.add_column("Command", style="bold green", width=14)
        table.add_column("Description")
        for c, d in [
            ("/help", "This message"),
            ("/clear", "Reset conversation"),
            ("/history", "Show conversation turns"),
            ("/tools", "List available tools"),
            ("/status", "Agent memory & task state"),
            ("/model", "Current LLM info"),
            ("/run <task>", "Execute via autonomous agent loop"),
            ("/exec <cmd>", "Run raw shell command"),
            ("/save", "Export session to file"),
            ("/quit", "Exit"),
        ]:
            table.add_row(c, d)
        console.print(table)
        console.print()
        return True

    if command == "/clear":
        conversation.clear()
        console.print("[bold green]✓ Context cleared.[/bold green]\n")
        return True

    if command == "/history":
        turns = conversation.get_turns_display()
        table = Table(title=f"Conversation ({len(turns)} messages)", border_style="dim")
        table.add_column("#", width=4, style="dim")
        table.add_column("Role", width=10)
        table.add_column("Preview")
        icons = {"system": "⚙", "user": "👤", "assistant": "🜏"}
        colors = {"system": "dim", "user": "green", "assistant": "cyan"}
        for t in turns:
            role = t["role"]
            table.add_row(str(t["i"]), f"[{colors.get(role, '')}]{icons.get(role, '•')} {role}[/]", t["preview"] + "…")
        console.print(table)
        console.print()
        return True

    if command == "/tools":
        table = Table(title=f"Tools ({len(TOOLS)})", border_style="dim")
        table.add_column("Tool", style="cyan bold")
        table.add_column("Module", style="dim")
        for name, fn in sorted(TOOLS.items()):
            table.add_row(name, fn.__module__)
        console.print(table)
        console.print()
        return True

    if command == "/status":
        try:
            memory = load_memory()
            summary = get_task_state_summary(memory)
            console.print(Panel(summary, title="Agent Status", border_style="cyan"))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        console.print()
        return True

    if command == "/model":
        console.print(f"  [bold]Model:[/bold]    [cyan]{OLLAMA_MODEL}[/cyan]")
        console.print(f"  [bold]Endpoint:[/bold] [dim]{OLLAMA_BASE_URL}[/dim]")
        console.print(f"  [bold]Project:[/bold]  [dim]{PROJECT_ROOT}[/dim]")
        console.print()
        return True

    if command == "/run":
        if not args:
            console.print("[yellow]Usage: /run <task description>[/yellow]\n")
            return True
        _run_agent_task(args)
        return True

    if command == "/exec":
        if not args:
            console.print("[yellow]Usage: /exec <shell command>[/yellow]\n")
            return True
        _exec_shell(args)
        return True

    if command == "/save":
        _save_session(conversation)
        return True

    console.print(f"[yellow]Unknown: {command}. Type /help[/yellow]\n")
    return True


def _run_agent_task(task: str) -> None:
    """Run the full autonomous agent loop with a production-grade Live UI."""
    try:
        from agent.loop import run_agent_loop
        from rich.spinner import Spinner
        from rich.table import Table

        console.print(f"\n[bold magenta]► AUTONOMOUS AGENT INITIATED[/bold magenta] [cyan]{task}[/cyan]\n")

        status_text = Text("Initializing...", style="dim")
        panel = Panel(status_text, title="[bold cyan]Agent Loop[/bold cyan]", border_style="cyan", padding=(1, 2))

        with Live(panel, console=console, refresh_per_second=10) as live:
            def progress_cb(event: dict) -> None:
                nonlocal status_text
                t = event.get("type", "")
                msg = event.get("message", "")
                step = event.get("step", 0)
                
                # Format specific events for the live panel
                if t == "tool_start":
                    tool = event.get('tool', 'unknown')
                    status_text = Text(f"[{step}] ⚙️ Executing tool: {tool}", style="yellow")
                elif t == "tool_result":
                    status_text = Text(f"[{step}] ✓ Tool completed", style="green")
                elif t == "tool_error":
                    status_text = Text(f"[{step}] ✗ Tool failed, auto-correcting...", style="red")
                elif t == "plan":
                    status_text = Text(f"[{step}] 📋 Planning steps...", style="blue")
                elif t == "action":
                    status_text = Text(f"[{step}] 🧠 Reasoning next move...", style="cyan")
                else:
                    status_text = Text(f"[{step}] {msg}", style="dim")
                
                # Update the live display
                live.update(Panel(status_text, title="[bold cyan]Agent Loop[/bold cyan]", border_style="cyan", padding=(1, 2)))

            result = run_agent_loop(task, progress_callback=progress_cb)

        if isinstance(result, dict):
            status = result.get("status", "completed")
            icon = "✓" if status != "blocked" else "⛔"
            console.print(Panel(
                "\n".join(f"  {k}: {str(v)[:200]}" for k, v in result.items()),
                title=f"{icon} Task {status}",
                border_style="green" if status != "blocked" else "red",
            ))
        else:
            console.print(f"[bold green]✓ Final Result:[/bold green] {str(result)[:1000]}")
    except Exception as e:
        console.print(f"[red]Agent error: {e}[/red]")
        logger.exception("Agent loop failed")
    console.print()


def _exec_shell(cmd: str) -> None:
    """Execute a raw shell command."""
    console.print(f"[dim]$ {cmd}[/dim]")
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=120, cwd=str(PROJECT_ROOT),
            env={**os.environ, "PAGER": "cat"},
        )
        if proc.stdout:
            console.print(proc.stdout.rstrip())
        if proc.stderr:
            console.print(f"[yellow]{proc.stderr.rstrip()}[/yellow]")
        if proc.returncode != 0:
            console.print(f"[red]exit {proc.returncode}[/red]")
    except subprocess.TimeoutExpired:
        console.print("[red]Timeout (120s)[/red]")
    except Exception as e:
        console.print(f"[red]{e}[/red]")
    console.print()


def _save_session(conversation: ConversationMemory) -> None:
    """Export the session to a JSON file."""
    out = STATE_DIR / f"session_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "exported_at": datetime.now().isoformat(),
        "model": OLLAMA_MODEL,
        "turns": conversation.turn_count,
        "messages": conversation.messages,
    }
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]✓ Session saved to {out}[/green]\n")


# ── Multi-line Input ─────────────────────────────────────────────────────
def read_input() -> str | None:
    """Read user input, supporting multi-line with triple-backtick blocks."""
    try:
        cwd = _compact_path(PROJECT_ROOT, 26)
        model = OLLAMA_MODEL.replace("qwen2.5-coder:", "qwen ")
        prompt = (
            "\033[38;5;242m>\033[0m "
            f"\033[48;5;208m\033[38;5;16m anubis \033[0m"
            f"\033[48;5;94m\033[38;5;230m {cwd} \033[0m"
            f"\033[48;5;24m\033[38;5;153m {model} \033[0m "
        )
        line = input(prompt).strip()
    except EOFError:
        return None
    except KeyboardInterrupt:
        console.print()
        return ""

    if not line:
        return ""

    # Multi-line: if user starts with ```, read until closing ```
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


# ── Banner ───────────────────────────────────────────────────────────────
ANUBIS_FACE = r"""
        .-.
       (o o)
      /  V  \
     /(  _  )\
       ^^ ^^
""".strip("\n")


def _compact_path(path: Path, max_len: int = 48) -> str:
    text = str(path)
    if len(text) <= max_len:
        return text
    return "..." + text[-(max_len - 3):]


def _tool_preview(limit: int = 14) -> str:
    preferred = [
        "read_file",
        "write_file",
        "search_code",
        "run_command",
        "scan_repo_tree",
        "git_status",
        "index_repository",
        "search_hermes_memory",
        "store_hermes_memory",
        "create_dynamic_tool",
        "developer_project_status",
        "run_project_tests",
        "autonomous_git_commit",
        "final",
    ]
    names = [name for name in preferred if name in TOOLS]
    names.extend(name for name in sorted(TOOLS) if name not in names)
    return ", ".join(names[:limit])


def _recent_activity() -> str:
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


def _banner_panel() -> Panel:
    left_width = 45
    right_width = 28
    left_lines = [
        (f"Anubis Code v{VERSION}", "bold orange1"),
        ("", "bright_black"),
        *[(line, "bright_white") for line in ANUBIS_FACE.splitlines()],
        ("", "bright_black"),
        (f"{OLLAMA_MODEL} · local Ollama agent", "bright_black"),
        (f"{len(TOOLS)} tools · max {MAX_STEPS} steps", "bright_black"),
        (_compact_path(PROJECT_ROOT, left_width), "bright_black"),
    ]
    right_lines = [
        ("Tips for getting started", "bold orange1"),
        ("Run /help to create", "bright_black"),
        ("edit, test, inspect", "bright_black"),
        ("", "bright_black"),
        ("Recent activity", "bold orange1"),
        (_recent_activity()[:right_width], "bright_black"),
        ("", "bright_black"),
        ("Endpoint", "bold orange1"),
        (OLLAMA_BASE_URL[:right_width], "bright_black"),
    ]

    height = max(len(left_lines), len(right_lines))
    left_lines.extend([("", "bright_black")] * (height - len(left_lines)))
    right_lines.extend([("", "bright_black")] * (height - len(right_lines)))

    layout = Text()
    for index, ((left, left_style), (right, right_style)) in enumerate(zip(left_lines, right_lines)):
        layout.append(f"{left:<{left_width}}", style=left_style)
        layout.append("│", style="orange1")
        layout.append(f" {right:<{right_width}}", style=right_style)
        if index < height - 1:
            layout.append("\n")

    return Panel(
        layout,
        border_style="orange1",
        box=box.SQUARE,
        padding=(0, 1),
    )


def print_banner():
    console.clear()
    sys.stdout.write(f"\033]0;Anubis Code - {OLLAMA_MODEL}\007")
    sys.stdout.flush()
    console.print(_banner_panel())
    console.print("[dim]Try /help, /model, /tools, or ask Anubis to inspect this repo.[/dim]\n")


# ── Main REPL ────────────────────────────────────────────────────────────
def repl() -> None:
    _setup_readline()
    print_banner()

    sys_prompt = CLI_SYSTEM_PROMPT.replace("{date}", datetime.now().strftime("%Y-%m-%d %H:%M"))
    conversation = ConversationMemory(sys_prompt)

    # Graceful Ctrl+C during streaming
    signal.signal(signal.SIGINT, lambda s, f: None)

    while True:
        user_input = read_input()

        if user_input is None:
            console.print("\n[dim]Session ended.[/dim]")
            break

        if not user_input:
            continue

        # 1. Slash commands
        if user_input.startswith("/"):
            if not handle_command(user_input, conversation):
                console.print("[dim]Session ended. Memory saved.[/dim]\n")
                break
            continue

        # 2. Intent routing (natural commands)
        intent = parse_intent(user_input)
        if intent:
            action, args = intent
            if action == "_status":
                handle_command("/status", conversation)
            else:
                execute_and_display(action, args, conversation, user_input)
            continue

        # 3. Auto-Routing to Agent Loop for complex tasks
        trigger_words = {"build", "create", "fix", "refactor", "analyze", "debug", "write", "implement"}
        first_word = user_input.split()[0].lower()
        if len(user_input.split()) > 8 or first_word in trigger_words:
            console.print("[dim]→ Auto-routing complex request to Autonomous Agent...[/dim]")
            _run_agent_task(user_input)
            continue

        # 4. LLM fallback (conversational)
        try:
            stream_response(conversation, user_input)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]\n")
            logger.exception("Stream failed")


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "serve":
            from app.main import main as run_server
            run_server()
            return
        if arg == "status":
            print(get_task_state_summary(load_memory()))
            return
        # Direct task mode
        task = " ".join(sys.argv[1:])
        _run_agent_task(task)
        return
    repl()


if __name__ == "__main__":
    main()
