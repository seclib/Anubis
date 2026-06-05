from __future__ import annotations

from pathlib import Path


def main() -> None:
    files = sorted(Path("src").rglob("*.py")) + sorted(Path("core").rglob("*.py"))
    print({"python_files": len(files), "largest": _largest(files)})


def _largest(files: list[Path]) -> str | None:
    if not files:
        return None
    return str(max(files, key=lambda path: len(path.read_text(encoding="utf-8").splitlines())))


if __name__ == "__main__":
    main()
