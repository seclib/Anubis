"""Multi-agent collaboration primitives for Anubis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.coder_agent import CODER_PROMPT
from agent.debugger_agent import DEBUGGER_PROMPT
from agent.tester_agent import TESTER_PROMPT
from config import (
    CODER_AGENT_MODEL,
    DEBUGGER_AGENT_MODEL,
    MEMORY_AGENT_MODEL,
    ORCHESTRATOR_AGENT_MODEL,
    PLANNER_AGENT_MODEL,
    REVIEWER_AGENT_MODEL,
    TESTER_AGENT_MODEL,
)
from llm.ollama import call_llm


ORCHESTRATOR_AGENT = "orchestrator_agent"
PLANNER_AGENT = "planner_agent"
CODER_AGENT = "coder_agent"
REVIEWER_AGENT = "reviewer_agent"
TESTER_AGENT = "tester_agent"
DEBUGGER_AGENT = "debugger_agent"
MEMORY_AGENT = "memory_agent"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role: str
    model: str
    prompt: str


AGENT_SPECS: dict[str, AgentSpec] = {
    ORCHESTRATOR_AGENT: AgentSpec(
        name=ORCHESTRATOR_AGENT,
        role=(
            "Main brain of the system: receive the user task, distribute work to specialized agents, "
            "coordinate steps, aggregate results, and manage retries and priorities."
        ),
        model=ORCHESTRATOR_AGENT_MODEL,
        prompt=(
            "You are orchestrator_agent, the main brain of Anubis. Receive the user task, distribute "
            "work to planner_agent, coder_agent, reviewer_agent, tester_agent, debugger_agent, and "
            "memory_agent, coordinate step order, aggregate their results, manage retries and priorities, "
            "and never ask humans for help."
        ),
    ),
    PLANNER_AGENT: AgentSpec(
        name=PLANNER_AGENT,
        role="Decompose the user task into concrete implementation and verification steps.",
        model=PLANNER_AGENT_MODEL,
        prompt=(
            "You are the planner_agent. Produce concise, executable plans grounded in repository context. "
            "Prefer small steps with clear success criteria."
        ),
    ),
    CODER_AGENT: AgentSpec(
        name=CODER_AGENT,
        role=(
            "Implementation specialist: modify code, create files, refactor existing code, "
            "and implement features with minimal clean changes."
        ),
        model=CODER_AGENT_MODEL,
        prompt=CODER_PROMPT,
    ),
    REVIEWER_AGENT: AgentSpec(
        name=REVIEWER_AGENT,
        role="Review intermediate results for correctness, regressions, and completion readiness.",
        model=REVIEWER_AGENT_MODEL,
        prompt=(
            "You are the reviewer_agent. Evaluate whether the work satisfies the task. "
            "Look for missed requirements, unsafe changes, and incomplete outcomes."
        ),
    ),
    TESTER_AGENT: AgentSpec(
        name=TESTER_AGENT,
        role=(
            "Validation specialist: execute tests, run validation commands, detect runtime errors, "
            "verify results, and return structured validation reports."
        ),
        model=TESTER_AGENT_MODEL,
        prompt=TESTER_PROMPT,
    ),
    DEBUGGER_AGENT: AgentSpec(
        name=DEBUGGER_AGENT,
        role=(
            "Autonomous failure recovery specialist: analyze stack traces, identify probable causes, "
            "propose corrections, and rerun fixes automatically."
        ),
        model=DEBUGGER_AGENT_MODEL,
        prompt=DEBUGGER_PROMPT,
    ),
    MEMORY_AGENT: AgentSpec(
        name=MEMORY_AGENT,
        role="Maintain shared memory, summarize collaboration, and preserve useful context.",
        model=MEMORY_AGENT_MODEL,
        prompt=(
            "You are the memory_agent. Keep compact shared context for the team: decisions, assumptions, "
            "tool outcomes, and next useful facts."
        ),
    ),
}


def get_agent(agent_name: str) -> AgentSpec:
    try:
        return AGENT_SPECS[agent_name]
    except KeyError as exc:
        raise ValueError(f"Unknown agent: {agent_name}") from exc


def agent_prompt(agent_name: str, task_prompt: str, collaboration_context: str = "") -> str:
    spec = get_agent(agent_name)
    context = collaboration_context.strip()
    context_text = f"\n\nShared multi-agent context:\n{context}" if context else ""
    return f"""{spec.prompt}

Dedicated role:
{spec.role}
{context_text}

Agent task:
{task_prompt}
"""


def call_agent(agent_name: str, task_prompt: str, collaboration_context: str = "") -> str:
    spec = get_agent(agent_name)
    prompt = agent_prompt(agent_name, task_prompt, collaboration_context)
    return call_llm(prompt, model=spec.model)


def agent_roster() -> list[dict[str, str]]:
    return [
        {
            "name": spec.name,
            "role": spec.role,
            "model": spec.model,
            "prompt": spec.prompt,
        }
        for spec in AGENT_SPECS.values()
    ]


def append_agent_message(
    memory: dict[str, Any],
    agent_name: str,
    message: str,
    *,
    phase: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "agent": agent_name,
        "role": get_agent(agent_name).role,
        "model": get_agent(agent_name).model,
        "phase": phase,
        "message": message,
    }
    if metadata:
        event["metadata"] = metadata
    memory.setdefault("agent_messages", []).append(event)
    memory["last_agent"] = agent_name
    return event


def collaboration_context(memory: dict[str, Any], limit: int = 8) -> str:
    messages = memory.get("agent_messages", [])
    if not isinstance(messages, list) or not messages:
        return "No prior multi-agent messages."

    lines: list[str] = []
    for message in messages[-limit:]:
        if not isinstance(message, dict):
            continue
        agent_name = message.get("agent", "unknown_agent")
        phase = message.get("phase", "unknown")
        text = str(message.get("message", ""))[:600]
        lines.append(f"- {agent_name} [{phase}]: {text}")

    return "\n".join(lines) if lines else "No prior multi-agent messages."


__all__ = [
    "AGENT_SPECS",
    "CODER_AGENT",
    "DEBUGGER_AGENT",
    "MEMORY_AGENT",
    "ORCHESTRATOR_AGENT",
    "PLANNER_AGENT",
    "REVIEWER_AGENT",
    "TESTER_AGENT",
    "AgentSpec",
    "agent_prompt",
    "agent_roster",
    "append_agent_message",
    "call_agent",
    "collaboration_context",
    "get_agent",
]
