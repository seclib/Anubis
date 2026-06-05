from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CliConfig:
    project_root: Path = Path(os.getenv("PROJECT_ROOT", "."))
    state_dir: Path = Path(os.getenv("ANUBIS_STATE_DIR", "state"))
    history_file: Path = Path(os.getenv("ANUBIS_CLI_HISTORY", "state/anubis_cli_history"))
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    ollama_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model: str = os.getenv("ANUBIS_LLM_MODEL", "qwen2.5-coder:7b")
    default_top_k: int = int(os.getenv("ANUBIS_CLI_TOP_K", "5"))


config = CliConfig()
