"""ANUBIS CLI package.

The package initializer is intentionally side-effect free during Phase 1 so
public entrypoints can import ``cli.main`` without touching legacy
``anubis.*`` modules.
"""

__all__: list[str] = []
