import asyncio
import json
import logging
import time
from collections import deque
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent.multi_agent import agent_roster
from backend.api.routes.skills import get_skills_dir
from backend.core.config import settings
from rag.shared.backend_legacy.chunker import chunk_note
from backend.vault.service import VaultService


router = APIRouter()
logger = logging.getLogger("anubis.api.brain")
LOG_LIMIT = 600
LOG_BUFFER: deque[dict[str, Any]] = deque(maxlen=LOG_LIMIT)


class BrainLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        LOG_BUFFER.append(
            {
                "timestamp": record.created,
                "component": record.name,
                "level": record.levelname,
                "message": self.format(record),
            }
        )


def install_log_handler() -> None:
    root_logger = logging.getLogger()
    if any(isinstance(handler, BrainLogHandler) for handler in root_logger.handlers):
        return
    handler = BrainLogHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(handler)


install_log_handler()


def reset_route_state() -> None:
    LOG_BUFFER.clear()


def _vault() -> VaultService:
    return VaultService()


def _directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def _latest_mtime(path: Path) -> float | None:
    latest: float | None = None
    if not path.exists():
        return latest
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        try:
            mtime = item.stat().st_mtime
        except OSError:
            continue
        latest = mtime if latest is None else max(latest, mtime)
    return latest


def _skill_count() -> int:
    skills_dir = get_skills_dir()
    if not skills_dir.exists():
        return 0
    return len([path for path in skills_dir.glob("*") if path.is_file() and path.suffix in {".md", ".json"}])


def _qdrant_collection() -> dict[str, Any]:
    collection_url = f"{settings.qdrant_url.rstrip('/')}/collections/{settings.qdrant_collection}"
    try:
        with urlopen(collection_url, timeout=0.45) as response:  # noqa: S310 - local operator-configured URL.
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "status": "unavailable",
            "url": settings.qdrant_url,
            "collection": settings.qdrant_collection,
            "embedding_count": 0,
            "detail": str(exc),
        }

    result = payload.get("result", {}) if isinstance(payload, dict) else {}
    points_count = result.get("points_count") or result.get("vectors_count") or 0
    return {
        "status": "running",
        "url": settings.qdrant_url,
        "collection": settings.qdrant_collection,
        "embedding_count": int(points_count),
        "detail": "Collection reachable",
    }


def _memory_overview() -> dict[str, Any]:
    vault = _vault()
    notes = vault.list_notes()
    chunk_count = 0
    for note in notes:
        try:
            chunk_count += len(chunk_note(note["path"], vault.read_note(note["path"])))
        except (OSError, ValueError):
            continue

    qdrant = _qdrant_collection()
    return {
        "vault": {
            "path": str(vault.vault_path),
            "size_bytes": _directory_size(vault.vault_path),
            "updated_at": _latest_mtime(vault.vault_path),
        },
        "notes": len(notes),
        "skills": _skill_count(),
        "chunks": chunk_count,
        "embeddings": qdrant["embedding_count"],
        "qdrant": qdrant,
    }


def _system_health(memory: dict[str, Any]) -> dict[str, Any]:
    qdrant = memory["qdrant"]
    agents = agent_roster()
    return {
        "backend": {"status": "running", "detail": "FastAPI dashboard endpoints are responding"},
        "qdrant": {"status": qdrant["status"], "detail": qdrant["detail"]},
        "agent": {"status": "ready" if agents else "unavailable", "detail": f"{len(agents)} agents registered"},
        "launcher": {
            "status": "observed-by-frontend",
            "detail": "Launcher process status is merged from Tauri when available",
        },
    }


def _agent_activity() -> dict[str, Any]:
    agents = agent_roster()
    now = time.time()
    return {
        "active_agents": [
            {
                "name": agent["name"],
                "role": agent["role"],
                "model": agent["model"],
                "status": "idle",
                "current_task": "Awaiting orchestration",
            }
            for agent in agents
        ],
        "current_tasks": [],
        "last_executions": [
            {
                "agent": agent["name"],
                "task": "Registered in multi-agent roster",
                "status": "ready",
                "started_at": now,
                "duration_ms": 0,
            }
            for agent in agents[:4]
        ],
    }


def _architecture() -> dict[str, Any]:
    return {
        "frontend": "React desktop dashboard",
        "backend": "FastAPI brain endpoints",
        "live_updates": "WebSocket /brain/ws",
        "modules": [
            {"id": "launcher", "label": "Launcher", "depends_on": ["backend", "qdrant", "agent"]},
            {"id": "backend", "label": "FastAPI", "depends_on": ["vault", "qdrant"]},
            {"id": "vault", "label": "Markdown Vault", "depends_on": []},
            {"id": "qdrant", "label": "Vector Memory", "depends_on": []},
            {"id": "agent", "label": "Agent Swarm", "depends_on": ["backend", "vault"]},
            {"id": "frontend", "label": "React UI", "depends_on": ["backend", "launcher"]},
        ],
    }


def build_brain_snapshot() -> dict[str, Any]:
    memory = _memory_overview()
    return {
        "timestamp": time.time(),
        "system_health": _system_health(memory),
        "memory": memory,
        "agent_activity": _agent_activity(),
        "logs": list(LOG_BUFFER)[-150:],
        "architecture": _architecture(),
    }


@router.get("/snapshot")
def brain_snapshot() -> dict[str, Any]:
    logger.info("brain snapshot requested")
    return build_brain_snapshot()


@router.get("/logs")
def brain_logs(component: str | None = None) -> list[dict[str, Any]]:
    logs = list(LOG_BUFFER)
    if component:
        logs = [entry for entry in logs if entry.get("component") == component]
    return logs[-150:]


@router.websocket("/ws")
async def brain_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    cursor = len(LOG_BUFFER)
    try:
        while True:
            snapshot = build_brain_snapshot()
            logs = list(LOG_BUFFER)
            await websocket.send_json(
                {
                    "type": "brain.snapshot",
                    "snapshot": snapshot,
                    "logs": logs[cursor:],
                }
            )
            cursor = len(logs)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
