from datetime import UTC, datetime

from backend.vault.service import VaultService


class MarkdownMemory:
    def __init__(self) -> None:
        self.vault = VaultService()

    def inject(self, text: str, target: str = "notes/inbox.md") -> str:
        try:
            existing = self.vault.read_note(target)
        except FileNotFoundError:
            existing = "# Inbox\n"
        timestamp = datetime.now(UTC).isoformat()
        self.vault.write_note(target, f"{existing.rstrip()}\n\n- [{timestamp}] {text}\n")
        return target
