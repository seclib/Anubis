from __future__ import annotations

from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANUBIS_", env_file=".env", extra="ignore")

    env: str = "development"
    rag_url: AnyHttpUrl = "http://127.0.0.1:8101"
    allowed_workspace: Path = Field(default_factory=lambda: Path("."))
    data_dir: Path = Field(default_factory=lambda: Path(".anubis"))
    llm_provider: str = "mock"
    request_timeout_seconds: float = 30.0
    log_level: str = "INFO"
