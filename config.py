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
WORKSPACE_ROOT = Path(
    os.getenv("WORKSPACE_ROOT", os.getenv("WORKSPACE_DIR", str(PROJECT_ROOT)))
).expanduser().resolve()

# LLM Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", OLLAMA_MODEL)
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "1h")
ORCHESTRATOR_AGENT_MODEL = os.getenv("ORCHESTRATOR_AGENT_MODEL", OLLAMA_MODEL)
PLANNER_AGENT_MODEL = os.getenv("PLANNER_AGENT_MODEL", OLLAMA_MODEL)
CODER_AGENT_MODEL = os.getenv("CODER_AGENT_MODEL", OLLAMA_MODEL)
REVIEWER_AGENT_MODEL = os.getenv("REVIEWER_AGENT_MODEL", OLLAMA_MODEL)
TESTER_AGENT_MODEL = os.getenv("TESTER_AGENT_MODEL", OLLAMA_MODEL)
DEBUGGER_AGENT_MODEL = os.getenv("DEBUGGER_AGENT_MODEL", OLLAMA_MODEL)
MEMORY_AGENT_MODEL = os.getenv("MEMORY_AGENT_MODEL", OLLAMA_MODEL)
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
EMBEDDING_TIMEOUT = int(os.getenv("EMBEDDING_TIMEOUT", "20"))
EMBEDDING_FALLBACK_ENABLED = os.getenv("EMBEDDING_FALLBACK_ENABLED", "true").lower() == "true"
VECTOR_STORE_FILE = Path(os.getenv("VECTOR_STORE_FILE", "state/vector_store.json"))
HERMES_MEMORY_ENABLED = os.getenv("HERMES_MEMORY_ENABLED", "true").lower() == "true"
HERMES_MEMORY_BACKEND = os.getenv("HERMES_MEMORY_BACKEND", "local").lower()
HERMES_MEMORY_FILE = Path(os.getenv("HERMES_MEMORY_FILE", "state/hermes_memory.json"))
OBSIDIAN_VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "state/obsidian_vault"))
OBSIDIAN_DAILY_MEMORY_DIR = os.getenv("OBSIDIAN_DAILY_MEMORY_DIR", "memories")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "hermes_memory")
REDIS_CACHE_ENABLED = os.getenv("REDIS_CACHE_ENABLED", "true").lower() == "true"
REDIS_CACHE_URL = os.getenv("REDIS_CACHE_URL", "redis://localhost:6379/0")
REDIS_CACHE_NAMESPACE = os.getenv("REDIS_CACHE_NAMESPACE", "anubis:query_cache")
REDIS_CACHE_TTL_SECONDS = int(os.getenv("REDIS_CACHE_TTL_SECONDS", "604800"))
QUERY_CACHE_ENABLED = os.getenv("QUERY_CACHE_ENABLED", "true").lower() == "true"
QUERY_CACHE_FILE = Path(os.getenv("QUERY_CACHE_FILE", "state/query_cache.json"))
QUERY_CACHE_HIT_THRESHOLD = float(os.getenv("QUERY_CACHE_HIT_THRESHOLD", "0.85"))

# Optional agent capabilities
BASE_CHAT_ENABLED = os.getenv("BASE_CHAT_ENABLED", "true").lower() == "true"
OSINT_CRAWLER_ENABLED = os.getenv("OSINT_CRAWLER_ENABLED", "false").lower() == "true"
OBSIDIAN_RAG_ENABLED = os.getenv("OBSIDIAN_RAG_ENABLED", "true").lower() == "true"
CODE_ASSIST_ENABLED = os.getenv("CODE_ASSIST_ENABLED", "true").lower() == "true"

# Agent Configuration
MAX_STEPS = int(os.getenv("MAX_STEPS", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
MAX_TOOL_RETRIES = int(os.getenv("MAX_TOOL_RETRIES", "3"))
TOOL_COMMAND_TIMEOUT = int(os.getenv("TOOL_COMMAND_TIMEOUT", "120"))
TOOL_COMMAND_MAX_LENGTH = int(os.getenv("TOOL_COMMAND_MAX_LENGTH", "4000"))
TOOL_OUTPUT_MAX_CHARS = int(os.getenv("TOOL_OUTPUT_MAX_CHARS", "20000"))
TOOL_AUDIT_FILE = Path(os.getenv("TOOL_AUDIT_FILE", "state/tool_audit.log"))
CONTINUOUS_RUN = os.getenv("CONTINUOUS_RUN", "true").lower() == "true"
AUTO_GIT_COMMIT_ENABLED = os.getenv("AUTO_GIT_COMMIT_ENABLED", "true").lower() == "true"
GIT_USE_TEMP_BRANCH = os.getenv("GIT_USE_TEMP_BRANCH", "false").lower() == "true"
GIT_TEMP_BRANCH_PREFIX = os.getenv("GIT_TEMP_BRANCH_PREFIX", "anubis/auto")
GIT_VALIDATION_COMMANDS = [
    command.strip()
    for command in os.getenv(
        "GIT_VALIDATION_COMMANDS",
        "python3 -m unittest discover -s tests",
    ).split("&&")
    if command.strip()
]

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
    "WORKSPACE_ROOT",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_FALLBACK_MODEL",
    "OLLAMA_NUM_CTX",
    "OLLAMA_KEEP_ALIVE",
    "ORCHESTRATOR_AGENT_MODEL",
    "PLANNER_AGENT_MODEL",
    "CODER_AGENT_MODEL",
    "REVIEWER_AGENT_MODEL",
    "TESTER_AGENT_MODEL",
    "DEBUGGER_AGENT_MODEL",
    "MEMORY_AGENT_MODEL",
    "LLM_TEMPERATURE",
    "LLM_MAX_TOKENS",
    "EMBEDDING_MODEL",
    "EMBEDDING_TIMEOUT",
    "EMBEDDING_FALLBACK_ENABLED",
    "VECTOR_STORE_FILE",
    "HERMES_MEMORY_ENABLED",
    "HERMES_MEMORY_BACKEND",
    "HERMES_MEMORY_FILE",
    "OBSIDIAN_VAULT_PATH",
    "OBSIDIAN_DAILY_MEMORY_DIR",
    "QDRANT_URL",
    "QDRANT_COLLECTION",
    "REDIS_CACHE_ENABLED",
    "REDIS_CACHE_URL",
    "REDIS_CACHE_NAMESPACE",
    "REDIS_CACHE_TTL_SECONDS",
    "QUERY_CACHE_ENABLED",
    "QUERY_CACHE_FILE",
    "QUERY_CACHE_HIT_THRESHOLD",
    "BASE_CHAT_ENABLED",
    "OSINT_CRAWLER_ENABLED",
    "OBSIDIAN_RAG_ENABLED",
    "CODE_ASSIST_ENABLED",
    "MAX_STEPS",
    "MAX_RETRIES",
    "MAX_TOOL_RETRIES",
    "TOOL_COMMAND_TIMEOUT",
    "TOOL_COMMAND_MAX_LENGTH",
    "TOOL_OUTPUT_MAX_CHARS",
    "TOOL_AUDIT_FILE",
    "CONTINUOUS_RUN",
    "AUTO_GIT_COMMIT_ENABLED",
    "GIT_USE_TEMP_BRANCH",
    "GIT_TEMP_BRANCH_PREFIX",
    "GIT_VALIDATION_COMMANDS",
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
