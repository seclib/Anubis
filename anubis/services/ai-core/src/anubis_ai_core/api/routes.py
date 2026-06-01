from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from anubis_tools import ToolDefinition, ToolRegistry

from anubis_ai_core.agent.loop_engine import AgentLoopEngine
from anubis_ai_core.api.dependencies import (
    get_agent_loop_engine,
    get_chat_service,
    get_multi_agent_orchestrator,
    get_tool_registry,
)
from anubis_ai_core.models.agent import AgentRunRequest, AgentRunResponse
from anubis_ai_core.models.chat import ChatRequest, ChatResponse
from anubis_ai_core.models.orchestration import OrchestratorRunRequest, OrchestratorRunResponse
from anubis_ai_core.orchestrator.engine import MultiAgentOrchestrator
from anubis_ai_core.orchestration.chat_service import ChatService

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-core"}


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return await service.handle(payload, request_id=request.state.request_id)


@router.get("/v1/tools", response_model=list[ToolDefinition])
async def list_tools(registry: ToolRegistry = Depends(get_tool_registry)) -> list[ToolDefinition]:
    return registry.list()


@router.post("/v1/agent/run", response_model=AgentRunResponse)
async def run_agent(
    payload: AgentRunRequest,
    request: Request,
    engine: AgentLoopEngine = Depends(get_agent_loop_engine),
) -> AgentRunResponse:
    return await engine.run(payload, request_id=request.state.request_id)


@router.post("/v1/orchestrator/run", response_model=OrchestratorRunResponse)
async def run_orchestrator(
    payload: OrchestratorRunRequest,
    request: Request,
    orchestrator: MultiAgentOrchestrator = Depends(get_multi_agent_orchestrator),
) -> OrchestratorRunResponse:
    return await orchestrator.run(payload, request_id=request.state.request_id)
