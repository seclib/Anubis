from __future__ import annotations

from fastapi import Request
from anubis_memory_sdk import ShortTermMemory
from anubis_prompt_engine import PromptEngine
from anubis_tools import ToolRegistry, create_default_registry

from anubis_ai_core.agent.loop_engine import AgentLoopEngine
from anubis_ai_core.agent.step_generator import AgentStepGenerator
from anubis_ai_core.agent.tool_dispatcher import ToolDispatcher
from anubis_ai_core.clients.llm import LlmClient, MockLlmClient
from anubis_ai_core.clients.rag import RagClient
from anubis_ai_core.core.config import Settings
from anubis_ai_core.memory.interface import AgentMemoryInterface
from anubis_ai_core.observability.agent_trace import AgentTraceLogger
from anubis_ai_core.orchestrator.critic_agent import CriticAgent
from anubis_ai_core.orchestrator.engine import MultiAgentOrchestrator
from anubis_ai_core.orchestrator.executor_agent import ExecutorAgent
from anubis_ai_core.orchestrator.memory_write_policy import MemoryWritePolicy
from anubis_ai_core.orchestrator.planner_agent import PlannerAgent
from anubis_ai_core.orchestrator.trace_logger import OrchestrationTraceLogger
from anubis_ai_core.orchestration.chat_service import ChatService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_llm_client() -> LlmClient:
    return MockLlmClient()


async def get_short_term_memory() -> ShortTermMemory:
    raise RuntimeError("Short-term memory must be resolved from app state")


async def get_tool_registry(request: Request) -> ToolRegistry:
    return request.app.state.tool_registry


async def get_chat_service(request: Request) -> ChatService:
    settings = get_settings(request)
    return ChatService(
        llm_client=await get_llm_client(),
        rag_client=RagClient(str(settings.rag_url), settings.request_timeout_seconds),
        memory=request.app.state.short_term_memory,
        prompt_engine=PromptEngine(),
    )


async def get_agent_loop_engine(request: Request) -> AgentLoopEngine:
    settings = get_settings(request)
    rag_client = RagClient(str(settings.rag_url), settings.request_timeout_seconds)
    memory = AgentMemoryInterface(rag_client=rag_client, data_dir=settings.data_dir)
    llm_client = await get_llm_client()
    dispatcher = ToolDispatcher(
        registry=request.app.state.tool_registry,
        memory=memory,
        request_id=request.state.request_id,
    )
    return AgentLoopEngine(
        state_manager=request.app.state.agent_state_manager,
        step_generator=AgentStepGenerator(llm_client),
        dispatcher=dispatcher,
        memory=memory,
        trace_logger=AgentTraceLogger(),
    )


async def get_multi_agent_orchestrator(request: Request) -> MultiAgentOrchestrator:
    settings = get_settings(request)
    rag_client = RagClient(str(settings.rag_url), settings.request_timeout_seconds)
    memory = AgentMemoryInterface(rag_client=rag_client, data_dir=settings.data_dir)
    llm_client = await get_llm_client()
    dispatcher = ToolDispatcher(
        registry=request.app.state.tool_registry,
        memory=memory,
        request_id=request.state.request_id,
    )
    return MultiAgentOrchestrator(
        planner=PlannerAgent(llm_client),
        executor=ExecutorAgent(llm_client, dispatcher),
        critic=CriticAgent(llm_client),
        session_manager=request.app.state.orchestration_session_manager,
        memory_write_policy=MemoryWritePolicy(),
        trace_logger=OrchestrationTraceLogger(),
    )
