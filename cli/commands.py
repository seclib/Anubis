from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime

from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import OLLAMA_BASE_URL, OLLAMA_MODEL, PROJECT_ROOT, STATE_DIR
from memory.state import get_task_state_summary, load_memory
from runtime.tool_registry import tool_registry
from cli.session import ConversationMemory
from cli.ui import console, logger


def handle_command(cmd: str, conversation: ConversationMemory) -> bool:
    parts = cmd.strip().split(None, 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command in ("/quit", "/exit", "/q"):
        return False

    if command == "/help":
        table = Table(title="Commands", border_style="dim", show_header=False)
        table.add_column("Command", style="bold green", width=14)
        table.add_column("Description")
        for item, description in [
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
            table.add_row(item, description)
        console.print(table)
        console.print()
        return True

    if command == "/clear":
        conversation.clear()
        console.print("[bold green]Context cleared.[/bold green]\n")
        return True

    if command == "/history":
        turns = conversation.get_turns_display()
        table = Table(title=f"Conversation ({len(turns)} messages)", border_style="dim")
        table.add_column("#", width=4, style="dim")
        table.add_column("Role", width=10)
        table.add_column("Preview")
        colors = {"system": "dim", "user": "green", "assistant": "cyan"}
        for turn in turns:
            role = str(turn["role"])
            table.add_row(str(turn["i"]), f"[{colors.get(role, '')}]{role}[/]", str(turn["preview"]) + "...")
        console.print(table)
        console.print()
        return True

    if command == "/tools":
        tools = tool_registry()
        table = Table(title=f"Tools ({len(tools)})", border_style="dim")
        table.add_column("Tool", style="cyan bold")
        table.add_column("Module", style="dim")
        for name, fn in sorted(tools.items()):
            table.add_row(name, fn.__module__)
        console.print(table)
        console.print()
        return True

    if command == "/status":
        try:
            memory = load_memory()
            summary = get_task_state_summary(memory)
            console.print(Panel(summary, title="Agent Status", border_style="cyan"))
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
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
        run_agent_task(args)
        return True

    if command == "/exec":
        if not args:
            console.print("[yellow]Usage: /exec <shell command>[/yellow]\n")
            return True
        exec_shell(args)
        return True

    if command == "/save":
        save_session(conversation)
        return True

    console.print(f"[yellow]Unknown: {command}. Type /help[/yellow]\n")
    return True


def run_agent_task(task: str) -> None:
    try:
        from runtime.agent_runner import run_agent_loop

        console.print(f"\n[bold magenta]> AUTONOMOUS AGENT[/bold magenta] [cyan]{task}[/cyan]\n")
        status_text = Text("Initializing...", style="dim")
        panel = Panel(status_text, title="[bold cyan]Agent Loop[/bold cyan]", border_style="cyan", padding=(1, 2))

        with Live(panel, console=console, refresh_per_second=10) as live:
            def progress_cb(event: dict) -> None:
                event_type = event.get("type", "")
                message = event.get("message", "")
                step = event.get("step", 0)

                if event_type == "tool_start":
                    text = Text(f"[{step}] Executing tool: {event.get('tool', 'unknown')}", style="yellow")
                elif event_type == "tool_result":
                    text = Text(f"[{step}] Tool completed", style="green")
                elif event_type == "tool_error":
                    text = Text(f"[{step}] Tool failed, auto-correcting...", style="red")
                elif event_type == "plan":
                    text = Text(f"[{step}] Planning steps...", style="blue")
                elif event_type == "action":
                    text = Text(f"[{step}] Reasoning next move...", style="cyan")
                else:
                    text = Text(f"[{step}] {message}", style="dim")

                live.update(Panel(text, title="[bold cyan]Agent Loop[/bold cyan]", border_style="cyan", padding=(1, 2)))

            result = run_agent_loop(task, progress_callback=progress_cb)

        if isinstance(result, dict):
            status = result.get("status", "completed")
            console.print(
                Panel(
                    "\n".join(f"  {key}: {str(value)[:200]}" for key, value in result.items()),
                    title=f"Task {status}",
                    border_style="green" if status != "blocked" else "red",
                )
            )
        else:
            console.print(f"[bold green]Final Result:[/bold green] {str(result)[:1000]}")
    except Exception as exc:
        console.print(f"[red]Agent error: {exc}[/red]")
        logger.exception("Agent loop failed")
    console.print()


def exec_shell(cmd: str) -> None:
    console.print(f"[dim]$ {cmd}[/dim]")
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT),
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
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
    console.print()


def save_session(conversation: ConversationMemory) -> None:
    out = STATE_DIR / f"session_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "exported_at": datetime.now().isoformat(),
        "model": OLLAMA_MODEL,
        "turns": conversation.turn_count,
        "messages": conversation.messages,
    }
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]Session saved to {out}[/green]\n")
