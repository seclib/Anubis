"""Repository introspection helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

IGNORED_PARTS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".turbo",
}

COMMON_ENTRYPOINTS = [
    "__main__.py",
    "main.py",
    "app.py",
    "run.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
    "main.go",
    "src/main.rs",
    "index.js",
    "index.ts",
    "server.js",
    "server.ts",
    "app.js",
    "app.ts",
    "Dockerfile",
]


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)


def _to_relative(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _iter_repo_paths(root: str = ".") -> tuple[Path, list[Path]]:
    root_path = Path(root)
    if not root_path.exists():
        return root_path, []

    paths = [
        path
        for path in sorted(root_path.rglob("*"))
        if not _is_ignored(path.relative_to(root_path))
    ]
    return root_path, paths


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _resolve_root(root: str = ".", path: str | None = None) -> str:
    return path if path is not None else root


def scan_repo_tree(root: str = ".", path: str | None = None) -> list[str]:
    """Return a filtered repository tree relative to *root*."""
    root = _resolve_root(root, path)
    root_path, paths = _iter_repo_paths(root)
    return [_to_relative(root_path, path) for path in paths]


def detect_project_type(root: str = ".", path: str | None = None) -> list[str]:
    """Heuristically detect the project type from common marker files."""
    root = _resolve_root(root, path)
    root_path = Path(root)
    _, repo_paths = _iter_repo_paths(root)
    detected: list[str] = []

    markers = {
        "Python": ["pyproject.toml", "requirements.txt", "setup.py", "manage.py"],
        "Node.js": ["package.json"],
        "TypeScript": ["tsconfig.json"],
        "Go": ["go.mod"],
        "Rust": ["Cargo.toml"],
        "Java": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "Docker": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
        "PHP": ["composer.json"],
        "Ruby": ["Gemfile"],
    }

    for project_type, files in markers.items():
        if any((root_path / name).exists() for name in files):
            detected.append(project_type)

    package_json = root_path / "package.json"
    if package_json.exists():
        data = _load_json(package_json) or {}
        deps = {
            **data.get("dependencies", {}),
            **data.get("devDependencies", {}),
        }
        if "next" in deps:
            detected.append("Next.js")
        if "react" in deps:
            detected.append("React")
        if "vue" in deps:
            detected.append("Vue")
        if "@angular/core" in deps:
            detected.append("Angular")

    pyproject = root_path / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(errors="ignore").lower()
        if "fastapi" in content:
            detected.append("FastAPI")
        if "django" in content:
            detected.append("Django")
        if "flask" in content:
            detected.append("Flask")

    requirements = root_path / "requirements.txt"
    if requirements.exists():
        content = requirements.read_text(errors="ignore").lower()
        if "fastapi" in content:
            detected.append("FastAPI")
        if "django" in content:
            detected.append("Django")
        if "flask" in content:
            detected.append("Flask")

    python_files = [path for path in repo_paths if path.is_file() and path.suffix == ".py"]
    js_files = [path for path in repo_paths if path.is_file() and path.suffix in {".js", ".mjs", ".cjs"}]
    ts_files = [path for path in repo_paths if path.is_file() and path.suffix in {".ts", ".tsx"}]

    if python_files and "Python" not in detected:
        detected.append("Python")
    if js_files and "Node.js" not in detected:
        detected.append("Node.js")
    if ts_files and "TypeScript" not in detected:
        detected.append("TypeScript")

    return _unique(detected)


def search_code(query: str, root: str = ".", path: str | None = None) -> list[str]:
    """Search code for *query* using ripgrep when available."""
    if not query:
        return []
    root = _resolve_root(root, path)

    rg_path = shutil.which("rg")
    if rg_path:
        result = subprocess.run(
            [rg_path, "-n", "--hidden", "--glob", "!.git", query, root],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip().splitlines() if result.stdout else []

    result = subprocess.run(
        ["grep", "-rHn", query, root],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip().splitlines() if result.stdout else []


def find_entrypoints(root: str = ".", path: str | None = None) -> list[str]:
    """Return probable entrypoints for running the project."""
    root = _resolve_root(root, path)
    root_path, paths = _iter_repo_paths(root)
    entrypoints: list[str] = []

    for relative_name in COMMON_ENTRYPOINTS:
        candidate = root_path / relative_name
        if candidate.exists():
            entrypoints.append(_to_relative(root_path, candidate))

    for path in paths:
        if path.is_file() and path.name in {"main.py", "app.py", "manage.py", "main.go"}:
            entrypoints.append(_to_relative(root_path, path))
        if path.is_file() and path.suffix in {".js", ".ts"} and path.name in {"index.js", "index.ts", "server.js", "server.ts"}:
            entrypoints.append(_to_relative(root_path, path))

    package_json = root_path / "package.json"
    if package_json.exists():
        data = _load_json(package_json) or {}
        main_file = data.get("main")
        if isinstance(main_file, str) and (root_path / main_file).exists():
            entrypoints.append(_to_relative(root_path, root_path / main_file))

        bin_section = data.get("bin")
        if isinstance(bin_section, str) and (root_path / bin_section).exists():
            entrypoints.append(_to_relative(root_path, root_path / bin_section))
        elif isinstance(bin_section, dict):
            for value in bin_section.values():
                if isinstance(value, str) and (root_path / value).exists():
                    entrypoints.append(_to_relative(root_path, root_path / value))

    cargo_toml = root_path / "Cargo.toml"
    if cargo_toml.exists() and (root_path / "src/main.rs").exists():
        entrypoints.append("src/main.rs")

    if (root_path / "pyproject.toml").exists() and (root_path / "__main__.py").exists():
        entrypoints.append("__main__.py")

    return _unique(entrypoints)


def find_file(name: str, root: str = ".", path: str | None = None) -> list[str]:
    """Find files whose names contain *name*."""
    root = _resolve_root(root, path)
    root_path, paths = _iter_repo_paths(root)
    return [
        _to_relative(root_path, path)
        for path in paths
        if path.is_file() and name in path.name
    ]


def get_file_tree(root: str = ".", path: str | None = None) -> list[str]:
    """Backward-compatible alias for the filtered repository tree."""
    return scan_repo_tree(root=root, path=path)


def scan_full_repo(root: str = ".", path: str | None = None) -> list[str]:
    """Backward-compatible alias for the repository scan."""
    return scan_repo_tree(root=root, path=path)


def detect_framework(root: str = ".", path: str | None = None) -> list[str]:
    """Return framework-level detections derived from project files."""
    root = _resolve_root(root, path)
    root_path = Path(root)
    frameworks: list[str] = []

    package_json = root_path / "package.json"
    if package_json.exists():
        data = _load_json(package_json) or {}
        deps = {
            **data.get("dependencies", {}),
            **data.get("devDependencies", {}),
        }
        if "next" in deps:
            frameworks.append("Next.js")
        if "react" in deps:
            frameworks.append("React")
        if "vue" in deps:
            frameworks.append("Vue")
        if "@angular/core" in deps:
            frameworks.append("Angular")
        if "express" in deps:
            frameworks.append("Express")

    for file_name, framework_name in (
        ("manage.py", "Django"),
        ("wsgi.py", "Django"),
        ("asgi.py", "Django"),
    ):
        if (root_path / file_name).exists():
            frameworks.append(framework_name)

    requirements = root_path / "requirements.txt"
    if requirements.exists():
        content = requirements.read_text(errors="ignore").lower()
        if "fastapi" in content:
            frameworks.append("FastAPI")
        if "flask" in content:
            frameworks.append("Flask")
        if "django" in content:
            frameworks.append("Django")

    pyproject = root_path / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(errors="ignore").lower()
        if "fastapi" in content:
            frameworks.append("FastAPI")
        if "flask" in content:
            frameworks.append("Flask")
        if "django" in content:
            frameworks.append("Django")

    return _unique(frameworks)


def detect_entrypoints(root: str = ".", path: str | None = None) -> list[str]:
    """Backward-compatible alias for entrypoint discovery."""
    return find_entrypoints(root=root, path=path)


__all__ = [
    "detect_entrypoints",
    "detect_framework",
    "detect_project_type",
    "find_entrypoints",
    "find_file",
    "get_file_tree",
    "scan_full_repo",
    "scan_repo_tree",
    "search_code",
]
