from pathlib import Path

from backend.core.config import settings
from backend.core.paths import ensure_inside


class VaultService:
    def __init__(self, vault_path: Path | None = None) -> None:
        self.vault_path = vault_path or settings.vault_path
        self.vault_path.mkdir(parents=True, exist_ok=True)

    def list_notes(self) -> list[dict[str, str]]:
        notes = []
        for path in sorted(self.vault_path.rglob("*.md")):
            rel = path.relative_to(self.vault_path).as_posix()
            notes.append({"path": rel, "title": path.stem})
        return notes

    def read_note(self, note_path: str) -> str:
        path = ensure_inside(self.vault_path, Path(note_path))
        return path.read_text(encoding="utf-8")

    def write_note(self, note_path: str, content: str) -> None:
        path = ensure_inside(self.vault_path, Path(note_path))
        if path.suffix != ".md":
            raise ValueError("Only Markdown notes can be written")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
