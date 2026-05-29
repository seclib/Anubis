from __future__ import annotations

import json
import time

from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from config import OLLAMA_MODEL
from llm.ollama import stream_chat
from memory.state import get_context_summary, load_memory
from cli.session import ConversationMemory
from cli.ui import console
from runtime.tool_registry import default_tool_executor


def stream_response(conversation: ConversationMemory, user_input: str) -> str:
    conversation.add_user(user_input)

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
    with Live(Markdown("|"), console=console, refresh_per_second=12, transient=False) as live:
        try:
            for token in stream_chat(conversation.messages, model=OLLAMA_MODEL):
                full_response += token
                token_count += 1
                live.update(Markdown(full_response + "|"))
        except KeyboardInterrupt:
            full_response += "\n\n*(interrupted)*"
            live.update(Markdown(full_response))

    elapsed = time.monotonic() - start
    tps = token_count / elapsed if elapsed > 0 else 0
    console.print(Text(f"  {token_count} tokens · {elapsed:.1f}s · {tps:.1f} t/s", style="dim"))
    console.print()

    conversation.add_assistant(full_response)
    return full_response


def execute_and_display(
    action: str,
    args: dict,
    conversation: ConversationMemory,
    user_input: str,
) -> None:
    console.print(f"  [bold magenta]> EXEC[/bold magenta] [cyan]{action}[/cyan] ", end="")
    console.print(f"[dim]{json.dumps(args, ensure_ascii=False)}[/dim]")

    result = default_tool_executor().execute(action, args)
    success = result.get("success", False)
    output = result.get("output", "")

    if isinstance(output, dict):
        out_str = output.get("stdout", "") or output.get("stderr", "") or str(output)
    else:
        out_str = str(output)

    display = out_str[:4000] + ("\n...[TRUNCATED]" if len(out_str) > 4000 else "")
    border = "green" if success else "red"
    icon = "OK" if success else "FAIL"
    console.print(
        Panel(
            display.strip() or "(empty output)",
            title=f"[bold]{icon} {action.upper()}[/bold]",
            border_style=border,
            padding=(0, 1),
        )
    )

    fact = f"[{action}] {user_input} -> {'OK' if success else 'FAIL'}: {out_str[:500]}"
    conversation.inject_fact(fact)
