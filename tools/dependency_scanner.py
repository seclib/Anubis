from __future__ import annotations

from pathlib import Path


def main() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    external_runtime_dependencies = [
        line.strip()
        for line in requirements.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    print(
        {
            "runtime_dependencies": external_runtime_dependencies,
            "pyproject_declares_empty_runtime_deps": "dependencies = []" in pyproject,
        }
    )
    if external_runtime_dependencies:
        raise SystemExit("unexpected runtime dependencies")


if __name__ == "__main__":
    main()
