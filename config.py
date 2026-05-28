"""
Configuration Module - Central configuration for the Anubis Agent
"""

import os
from pathlib import Path


def _normalize_api_base_path(value: str | None, default: str = "/v1") -> str:
    raw_value = (value or default).strip()
    if not raw_value or raw_value == "/":
        return ""

    if not raw_value.startswith("/"):
        raw_value = f"/{raw_value}"

    return raw_value.rstrip("/")


# Project root
PROJECT_ROOT = Path(
    os.getenv("PROJECT_ROOT", str(Path(__file__).parent.absolute()))
).expanduser().resolve()

# LLM Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))

# Agent Configuration
MAX_STEPS = int(os.getenv("MAX_STEPS", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
MAX_TOOL_RETRIES = int(os.getenv("MAX_TOOL_RETRIES", "3"))
CONTINUOUS_RUN = os.getenv("CONTINUOUS_RUN", "true").lower() == "true"

# OpenAI-compatible API
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_BASE_PATH = _normalize_api_base_path(os.getenv("API_BASE_PATH", "/v1"))
API_MODEL_ID = os.getenv("API_MODEL_ID", "claude-code-local")
API_MODEL_NAME = os.getenv("API_MODEL_NAME", "Claude Code Local Agent")
API_KEY = os.getenv("API_KEY", "")
API_AUTH_REQUIRED = os.getenv("API_AUTH_REQUIRED", "false").lower() == "true"

# State and Memory
STATE_DIR = PROJECT_ROOT / "state"
MEMORY_FILE = STATE_DIR / "runtime.json"

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# Development
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

__all__ = [
    "PROJECT_ROOT",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "LLM_TEMPERATURE",
    "LLM_MAX_TOKENS",
    "MAX_STEPS",
    "MAX_RETRIES",
    "MAX_TOOL_RETRIES",
    "CONTINUOUS_RUN",
    "API_HOST",
    "API_PORT",
    "API_BASE_PATH",
    "API_MODEL_ID",
    "API_MODEL_NAME",
    "API_KEY",
    "API_AUTH_REQUIRED",
    "STATE_DIR",
    "MEMORY_FILE",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "DEBUG",
]
