from __future__ import annotations

import signal
import sys
from datetime import datetime

from config import STATE_DIR
from memory.state import get_task_state_summary, load_memory
from cli.commands import handle_command, run_agent_task
from cli.input import read_input, setup_readline
from cli.intent import parse_intent
from cli.renderer import execute_and_display, stream_response
from cli.session import CLI_SYSTEM_PROMPT, ConversationMemory
from cli.theme import print_banner
from cli.ui import configure_logging, console, logger


def repl() -> None:
    configure_logging()
    setup_readline()
    print_banner()

    sys_prompt = CLI_SYSTEM_PROMPT.replace("{date}", datetime.now().strftime("%Y-%m-%d %H:%M"))
    conversation = ConversationMemory(sys_prompt)

    signal.signal(signal.SIGINT, lambda _signal, _frame: None)

    while True:
        user_input = read_input()

        if user_input is None:
            console.print("\n[dim]Session ended.[/dim]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            if not handle_command(user_input, conversation):
                console.print("[dim]Session ended. Memory saved.[/dim]\n")
                break
            continue

        intent = parse_intent(user_input)
        if intent:
            action, args = intent
            if action == "_status":
                handle_command("/status", conversation)
            else:
                execute_and_display(action, args, conversation, user_input)
            continue

        trigger_words = {"build", "create", "fix", "refactor", "analyze", "debug", "write", "implement"}
        first_word = user_input.split()[0].lower()
        if len(user_input.split()) > 8 or first_word in trigger_words:
            console.print("[dim]-> Auto-routing complex request to Autonomous Agent...[/dim]")
            run_agent_task(user_input)
            continue

        try:
            stream_response(conversation, user_input)
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]\n")
            logger.exception("Stream failed")


def main() -> None:
    configure_logging()
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
        task = " ".join(sys.argv[1:])
        run_agent_task(task)
        return
    repl()

