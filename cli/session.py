from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config import PROJECT_ROOT, STATE_DIR
from agent.prompts import SYSTEM_PROMPT

MAX_CONTEXT_MESSAGES = 40

CLI_SYSTEM_PROMPT = f"""{SYSTEM_PROMPT}

ADDITIONAL CLI RULES:
- You are in interactive terminal mode. Be concise and technical.
- When the user asks a direct question, answer it with Markdown.
- For tool execution, output the standard JSON action block.
- Current working directory: {PROJECT_ROOT}
- Current date: {{date}}
""".strip()


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
            ctx = "[BACKGROUND CONTEXT - silent tool results]\n" + "\n".join(
                f"- {fact}" for fact in self._background_facts[-8:]
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
        self._messages = [
            message
            for message in self._messages
            if not (message["role"] == "system" and message is not self._system_msg)
        ]
        self._messages.insert(1, {"role": "system", "content": context})

    def inject_fact(self, fact: str) -> None:
        self._background_facts.append(fact)
        if len(self._background_facts) > 20:
            self._background_facts = self._background_facts[-20:]

    def clear(self) -> None:
        self._messages = [self._system_msg]
        self._background_facts.clear()

    def get_turns_display(self) -> list[dict[str, str | int]]:
        return [
            {
                "i": i,
                "role": message["role"],
                "preview": message["content"][:100].replace("\n", " "),
            }
            for i, message in enumerate(self._messages)
        ]

    def _trim(self) -> None:
        non_system = [message for message in self._messages if message["role"] != "system"]
        system_msgs = [message for message in self._messages if message["role"] == "system"]
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
            with open(self._session_file, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

