from __future__ import annotations

from fastapi import APIRouter

from anubis_kernel.agent.loop import AgentLoop
from anubis_kernel.agent.schemas import AgentRunRequest, AgentRunResponse
from anubis_kernel.memory.store import InMemoryStore
from anubis_kernel.sandbox.executor import FunctionSandbox
from anubis_kernel.tools.dispatcher import ToolDispatcher
from anubis_kernel.tools.registry import create_registry

router = APIRouter()

_memory = InMemoryStore()
_sandbox = FunctionSandbox()
_dispatcher = ToolDispatcher(registry=create_registry(), sandbox=_sandbox)
_agent = AgentLoop(dispatcher=_dispatcher, memory=_memory)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "anubis-kernel"}


@router.post("/v1/agent/run", response_model=AgentRunResponse)
async def run_agent(payload: AgentRunRequest) -> AgentRunResponse:
    return await _agent.run(payload)
