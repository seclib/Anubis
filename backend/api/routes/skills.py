import asyncio
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent.skill_ecosystem_graph import build_skill_ecosystem_graph, update_skill_ecosystem_graph


router = APIRouter()
SKILLS_DIR = Path(".agents/skills")


@lru_cache
def get_skills_dir() -> Path:
    return SKILLS_DIR


def reset_route_state() -> None:
    get_skills_dir.cache_clear()


def _skill_files_signature(skills_dir: Path) -> dict[str, float]:
    if not skills_dir.exists():
        return {}
    return {
        str(path): path.stat().st_mtime
        for path in sorted(skills_dir.glob("*"))
        if path.is_file() and path.suffix in {".md", ".json"}
    }


def _read_markdown(node: dict[str, Any]) -> str:
    path = node.get("path")
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _graph_payload(previous_graph: dict[str, Any] | None = None) -> dict[str, Any]:
    skills_dir = get_skills_dir()
    graph = (
        update_skill_ecosystem_graph(previous_graph, skills_dir)
        if previous_graph is not None
        else build_skill_ecosystem_graph(skills_dir)
    )
    for node in graph.get("nodes", []):
        if isinstance(node, dict) and node.get("type") == "skill":
            node["markdown"] = _read_markdown(node)
    graph.setdefault("insights", {})["newly_created_skills"] = [
        node_id
        for node_id in graph.get("changes", {}).get("added_nodes", [])
        if any(node.get("id") == node_id and node.get("type") == "skill" for node in graph.get("nodes", []))
    ]
    return graph


@router.get("/skills")
def list_skills() -> list[dict[str, Any]]:
    graph = _graph_payload()
    return [node for node in graph["nodes"] if node.get("type") == "skill"]


@router.get("/skill-graph")
def skill_graph() -> dict[str, Any]:
    return _graph_payload()


@router.get("/skill-updates")
async def skill_updates() -> StreamingResponse:
    async def events():
        previous_graph = _graph_payload()
        previous_signature = _skill_files_signature(get_skills_dir())
        yield f"event: skill-graph\ndata: {json.dumps(previous_graph)}\n\n"

        while True:
            await asyncio.sleep(2)
            signature = _skill_files_signature(get_skills_dir())
            if signature == previous_signature:
                yield ": keepalive\n\n"
                continue
            next_graph = _graph_payload(previous_graph)
            previous_graph = next_graph
            previous_signature = signature
            yield f"event: skill-graph\ndata: {json.dumps(next_graph)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")

