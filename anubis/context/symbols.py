from __future__ import annotations

from pathlib import Path
import re


LANGUAGES = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".md": "markdown",
}


def detect_language(path: Path) -> str:
    return LANGUAGES.get(path.suffix.lower(), path.suffix.lower().lstrip(".") or "text")


def extract_file_metadata(path: Path, language: str) -> tuple[list[str], list[str], list[str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], [], []
    return extract_symbols(text, language), extract_imports(text, language), extract_exports(text, language)


def extract_symbols(text: str, language: str) -> list[str]:
    patterns = [
        r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:(]",
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
        r"^\s*(?:export\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*",
        r"^\s*(?:export\s+)?const\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=",
    ]
    symbols: list[str] = []
    for pattern in patterns:
        symbols.extend(re.findall(pattern, text, flags=re.MULTILINE))
    return _unique(symbols)


def extract_imports(text: str, language: str) -> list[str]:
    imports: list[str] = []
    imports.extend(re.findall(r"^\s*import\s+(.+)$", text, flags=re.MULTILINE))
    imports.extend(re.findall(r"^\s*from\s+([A-Za-z0-9_./]+)\s+import\s+", text, flags=re.MULTILINE))
    imports.extend(re.findall(r"require\(['\"]([^'\"]+)['\"]\)", text))
    imports.extend(re.findall(r"use\s+([A-Za-z0-9_:]+)", text))
    return _unique([item.strip() for item in imports if item.strip()])


def extract_exports(text: str, language: str) -> list[str]:
    exports: list[str] = []
    exports.extend(re.findall(r"^\s*export\s+(?:default\s+)?(?:class|function|const)\s+([A-Za-z_$][A-Za-z0-9_$]*)", text, flags=re.MULTILINE))
    exports.extend(re.findall(r"^\s*__all__\s*=\s*\[([^\]]+)\]", text, flags=re.MULTILINE))
    return _unique([item.strip() for item in exports if item.strip()])


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


__all__ = ["detect_language", "extract_exports", "extract_file_metadata", "extract_imports", "extract_symbols"]
