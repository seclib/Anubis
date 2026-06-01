import logging
from functools import lru_cache

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.agent.loop import AgentLoop


router = APIRouter()
logger = logging.getLogger("anubis.api.agent")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


@lru_cache
def get_agent() -> AgentLoop:
    return AgentLoop()


def reset_route_state() -> None:
    """Clear cached route services for tests and config reloads."""
    get_agent.cache_clear()


@router.post("/chat")
def chat(payload: ChatRequest) -> dict[str, object]:
    result = get_agent().chat(payload.message)
    logger.info("agent chat chars=%s chunks=%s", len(payload.message), len(result.get("chunks_used", [])))
    return result
