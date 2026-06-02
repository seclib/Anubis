from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    vault_path: Path = Field(
        default=Path("vault"),
        validation_alias=AliasChoices("ANUBIS_VAULT_PATH", "OBSIDIAN_VAULT_PATH"),
    )
    skills_path: Path = Field(default=Path("vault/skills"), validation_alias="ANUBIS_SKILLS_PATH")
    project_root: Path = Field(default=Path("."), validation_alias="PROJECT_ROOT")
    qdrant_url: str = Field(default="http://localhost:6333", validation_alias="QDRANT_URL")
    qdrant_collection: str = Field(default="anubis_chunks", validation_alias="QDRANT_COLLECTION")
    embedding_model: str = Field(default="bge-m3", validation_alias="ANUBIS_EMBEDDING_MODEL")
    llm_model: str = Field(default="qwen2.5-coder:7b", validation_alias="ANUBIS_LLM_MODEL")
    ollama_url: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_BASE_URL")
    enable_watcher: bool = Field(default=True, validation_alias="ANUBIS_ENABLE_WATCHER")
    tool_timeout_seconds: int = Field(default=30, validation_alias="ANUBIS_TOOL_TIMEOUT_SECONDS")
    tool_log_path: Path = Field(default=Path("state/backend_tool_audit.jsonl"), validation_alias="ANUBIS_TOOL_LOG_PATH")
    allowed_commands: list[str] = ["git", "python3", "python", "pytest", "ls", "sed", "rg", "cat", "pwd"]
    allowed_origins: list[str] = ["http://localhost:1420", "tauri://localhost"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
