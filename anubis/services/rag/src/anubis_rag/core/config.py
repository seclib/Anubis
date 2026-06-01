from __future__ import annotations

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANUBIS_", env_file=".env", extra="ignore")

    qdrant_url: AnyHttpUrl = "http://127.0.0.1:6333"
    qdrant_collection: str = "anubis_memory"
    embedding_dimensions: int = 384
    chunk_size: int = 1200
    chunk_overlap: int = 160
    log_level: str = "INFO"
