from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    vault_path: Path = Field(default=Path("vault"), validation_alias="ANUBIS_VAULT_PATH")
    qdrant_url: str = Field(default="http://localhost:6333", validation_alias="QDRANT_URL")
    qdrant_collection: str = Field(default="anubis_chunks", validation_alias="QDRANT_COLLECTION")
    embedding_model: str = Field(default="bge-m3", validation_alias="ANUBIS_EMBEDDING_MODEL")
    llm_model: str = Field(default="qwen2.5-coder:7b", validation_alias="ANUBIS_LLM_MODEL")
    ollama_url: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_BASE_URL")
    allowed_origins: list[str] = ["http://localhost:1420", "tauri://localhost"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
