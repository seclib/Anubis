from pathlib import Path


def ensure_inside(base: Path, candidate: Path) -> Path:
    root = base.resolve()
    resolved = (base / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("Path escapes the vault")
    return resolved
