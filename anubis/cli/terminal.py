from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterable

from anubis.core.session_events import SessionEvent


class TerminalRenderer:
    """Plain Claude-Code-like renderer for live session events."""

    def __init__(self, output_fn: Callable[[str], None] | None = None) -> None:
        if output_fn is None:
            output_fn = _write_exact
        self.output_fn = output_fn
        self._assistant_open = False

    def render_stream(self, events: Iterable[SessionEvent]) -> str:
        final_result = ""
        for event in events:
            rendered = self.render_event(event)
            if rendered:
                self.output_fn(rendered)
            if event.type == "session.done":
                final_result = str(event.payload.get("result") or "")
        if self._assistant_open:
            self.output_fn("")
            self._assistant_open = False
        return final_result

    def render_event(self, event: SessionEvent) -> str:
        if event.type == "session.started":
            return f"Task: {event.payload.get('task', '')}\n"
        if event.type == "model.routed":
            return f"Model: {event.payload.get('model')} ({event.message})\n"
        if event.type == "agent.message" and "plan" in event.payload:
            lines = ["Plan:"]
            lines.extend(f"  {index}. {step}" for index, step in enumerate(event.payload["plan"], start=1))
            return "\n".join(lines) + "\n"
        if event.type == "memory.retrieved":
            items = event.payload.get("items") or []
            return f"Memory: {len(items)} item(s) recalled\n"
        if event.type == "tool.request":
            return f"Tool: {event.payload.get('tool')} {json.dumps(event.payload.get('args') or {}, ensure_ascii=False)}\n"
        if event.type in {"tool.result", "tool.error"}:
            result = event.payload.get("result") or {}
            status = "ok" if result.get("success") else "failed"
            return f"Tool result: {result.get('tool')} {status}\n"
        if event.type == "guardrail.triggered":
            return f"Guardrail: {event.message}\n"
        if event.type == "error":
            return f"Error: {event.message}\n"
        if event.type == "assistant.token":
            self._assistant_open = True
            return str(event.payload.get("text") or event.message)
        if event.type == "session.done":
            return "\nDone.\n"
        return ""


def _write_exact(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


__all__ = ["TerminalRenderer"]
