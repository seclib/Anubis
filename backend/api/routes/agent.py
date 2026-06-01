from fastapi import APIRouter
from pydantic import BaseModel

from backend.agent.loop import AgentLoop


router = APIRouter()
agent = AgentLoop()


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
def chat(payload: ChatRequest) -> dict[str, object]:
    return agent.chat(payload.message)
