"""Autonomous agent loop with an explicit state machine."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from agent.coder_agent import build_coder_context, create_coder_state
from agent.debugger_agent import (
    build_debugger_context,
    create_debugger_state,
    normalize_debugger_report,
)
from agent.memory import append_event, get_context_summary, load_memory, save_memory
from agent.multi_agent import (
    CODER_AGENT,
    DEBUGGER_AGENT,
    MEMORY_AGENT,
    ORCHESTRATOR_AGENT,
    PLANNER_AGENT,
    REVIEWER_AGENT,
    TESTER_AGENT,
    agent_roster,
    append_agent_message,
    call_agent,
    collaboration_context,
)
from agent.orchestrator_agent import (
    build_orchestrator_context,
    create_orchestrator_state,
    ensure_orchestrator_state,
    record_assignment,
    record_result,
    record_retry,
    select_agent_for_phase,
)
from agent.parser import parse_action
from agent.planner import plan_steps
from agent.prompts import AUTONOMY_RULES, SYSTEM_PROMPT
from agent.reviewer_agent import (
    build_reviewer_context,
    create_reviewer_state,
    normalize_review_report,
)
from agent.streaming import short_text
from agent.tester_agent import (
    build_tester_context,
    create_tester_state,
    normalize_validation_report,
)
from agent.vector_memory import index_agent_history, retrieve_context
from config import CONTINUOUS_RUN, MAX_RETRIES, MAX_STEPS as CONFIG_MAX_STEPS, MAX_TOOL_RETRIES
from executor.tool_executor import execute_tool

logger = logging.getLogger(__name__)

MAX_STEPS = CONFIG_MAX_STEPS
MAX_SELF_HEALING_RETRIES = max(0, min(MAX_TOOL_RETRIES, 3))
MAX_BLOCKED_CYCLES = 3

STATE_INIT = "INIT"
STATE_ANALYZE = "ANALYZE"
STATE_PLAN = "PLAN"
STATE_EXECUTE = "EXECUTE"
STATE_VERIFY = "VERIFY"
STATE_FIX = "FIX"
STATE_COMPLETE = "COMPLETE"

TOOL_SPECS = {
    "read_file": {"path": "<path>"},
    "write_file": {"path": "<path>", "content": "<text>"},
    "list_files": {"path": "<path>"},
    "run_command": {"cmd": "<shell command>"},
    "search_code": {"query": "<pattern>", "path": "<optional path>"},
    "scan_repo_tree": {"root": "<optional path>"},
    "detect_project_type": {"root": "<optional path>"},
    "find_entrypoints": {"root": "<optional path>"},
    "find_file": {"name": "<filename>"},
    "get_file_tree": {"path": "<path>"},
    "index_repository": {"root": "<optional path>", "force": False},
    "semantic_search": {"query": "<semantic query>", "top_k": 5, "kind": "<optional kind>"},
    "retrieve_context": {"query": "<semantic query>", "top_k": 5},
    "final": {"result": "<result>"},
}

ProgressCallback = Callable[[dict[str, Any]], None]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tool_specs_text() -> str:
    return "\n".join(
        f"- {tool_name}: {json.dumps(args, ensure_ascii=False)}"
        for tool_name, args in TOOL_SPECS.items()
    )


def _short(value: Any, limit: int = 1200) -> str:
    return short_text(value, limit)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
        return default
    return bool(value)


def _emit_progress(
    progress_callback: ProgressCallback | None,
    event_type: str,
    message: str,
    **data: Any,
) -> None:
    if progress_callback is None:
        return

    event = {
        "type": event_type,
        "message": message,
        "timestamp": _now_iso(),
    }
    if data:
        event.update(data)

    try:
        progress_callback(event)
    except Exception:
        logger.exception("Progress callback failed for event '%s'", event_type)


def _normalize_llm_action(action: dict[str, Any]) -> dict[str, Any]:
    uncertainty = str(action.get("uncertainty", "medium")).lower()
    if uncertainty not in {"low", "medium", "high"}:
        uncertainty = "medium"

    intent = str(action.get("intent", action.get("action", "act"))).lower()
    if intent not in {"plan", "act", "fix", "final"}:
        intent = "act"

    tool = action.get("tool", "")
    if tool is None:
        tool = ""
    tool = str(tool)

    next_action = action.get("next_action", action.get("next_step", ""))
    normalized = {
        **action,
        "uncertainty": uncertainty,
        "intent": intent,
        "action": intent,
        "tool": tool,
        "args": action.get("args", {}),
        "reason": str(action.get("reason", "")),
        "next_action": str(next_action),
        "next_step": str(next_action),
    }
    return normalized


def _set_state(memory: dict[str, Any], state: str, status: str | None = None) -> None:
    memory["state"] = state
    memory["updated_at"] = _now_iso()
    memory.setdefault("progression", {})
    memory["progression"]["state"] = state
    if status:
        memory["status"] = status
        memory["progression"]["status"] = status


def _initial_memory(task: str, use_planner: bool) -> dict[str, Any]:
    previous = load_memory()
    memory = {
        "tasks": list(previous.get("tasks", [])),
        "actions": list(previous.get("actions", [])),
        "tool_results": list(previous.get("tool_results", [])),
        "errors": list(previous.get("errors", [])),
        "progression": {
            "status": "running",
            "state": STATE_INIT,
            "current_step": 0,
            "completed_steps": 0,
            "max_steps": MAX_STEPS,
            "percent": 0,
        },
        "task": task,
        "task_analysis": None,
        "status": "running",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "completed_at": None,
        "max_steps": MAX_STEPS,
        "continuous_run": CONTINUOUS_RUN,
        "use_planner": use_planner,
        "state": STATE_INIT,
        "analysis_round": 0,
        "cycle": 1,
        "step_in_cycle": 0,
        "total_steps": 0,
        "consecutive_failures": 0,
        "successful_tools": 0,
        "successful_tools_at_cycle_start": 0,
        "cycles_without_progress": 0,
        "blockage_reason": "",
        "plan": [],
        "steps": [],
        "last_action": None,
        "last_result": None,
        "last_verification": None,
        "final_result": None,
        "pending_final": None,
        "repo_context": None,
        "agents": agent_roster(),
        "orchestration": create_orchestrator_state(task),
        "coder_agent": create_coder_state(),
        "debugger_agent": create_debugger_state(),
        "reviewer_agent": create_reviewer_state(),
        "tester_agent": create_tester_state(),
        "last_validation_report": None,
        "last_debugger_report": None,
        "last_review_report": None,
        "agent_messages": [],
        "last_agent": None,
        "collaboration_summary": "",
        "architecture_summary": "",
        "repo_analysis_round": 0,
        "strategy_change_required": False,
        "strategy_change_reason": "",
        "blocked_retry": None,
        "last_tool_analysis": None,
        "last_repo_analysis": None,
        "self_healing": {
            "max_tool_retries": MAX_SELF_HEALING_RETRIES,
            "persistent_failures": 0,
            "last_failure": None,
        },
    }
    return memory


def _record_event(
    memory: dict[str, Any],
    step: int,
    action: str,
    tool: str,
    args: Any,
    result: dict[str, Any],
    reason: str = "",
    next_step: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    event = {
        "step": step,
        "cycle": memory.get("cycle", 1),
        "cycle_step": memory.get("step_in_cycle", 0),
        "state": memory.get("state"),
        "action": action,
        "tool": tool,
        "args": args,
        "reason": reason,
        "next_step": next_step,
        "result": result,
    }
    if metadata:
        event.update(metadata)
    append_event(memory, event)


def _soft_limit_reached(memory: dict[str, Any]) -> bool:
    return int(memory.get("step_in_cycle", 0)) >= MAX_STEPS


def _mark_progress(memory: dict[str, Any], reason: str = "") -> None:
    memory["successful_tools"] = int(memory.get("successful_tools", 0)) + 1
    memory["cycles_without_progress"] = 0
    memory["blockage_reason"] = ""
    memory.setdefault("progression", {})
    memory["progression"]["last_progress_reason"] = reason
    memory["progression"]["successful_tools"] = memory["successful_tools"]


def _stop_for_total_blockage(
    memory: dict[str, Any],
    reason: str,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    memory["blockage_reason"] = reason
    memory["completed_at"] = _now_iso()
    memory["final_result"] = {
        "status": "blocked",
        "reason": reason,
        "cycles": memory.get("cycle", 1),
        "steps": len(memory.get("steps", [])),
        "last_result": memory.get("last_result"),
    }
    _set_state(memory, STATE_COMPLETE, status="blocked")
    _emit_progress(
        progress_callback,
        "blocked",
        f"Agent blocked: {reason}",
        state=STATE_COMPLETE,
        reason=reason,
        final_result=memory["final_result"],
    )
    save_memory(memory)
    return memory["final_result"]


def _reset_cycle(memory: dict[str, Any], reason: str) -> bool:
    successful_tools = int(memory.get("successful_tools", 0))
    cycle_start_successes = int(memory.get("successful_tools_at_cycle_start", 0))
    progressed = successful_tools > cycle_start_successes

    if progressed:
        memory["cycles_without_progress"] = 0
        memory["blockage_reason"] = ""
    else:
        memory["cycles_without_progress"] = int(memory.get("cycles_without_progress", 0)) + 1
        memory["blockage_reason"] = (
            f"No meaningful progress for {memory['cycles_without_progress']} cycle(s): {reason}"
        )

    memory["cycle"] = int(memory.get("cycle", 1)) + 1
    memory["step_in_cycle"] = 0
    memory["successful_tools_at_cycle_start"] = successful_tools
    memory.setdefault("progression", {})
    memory["progression"]["current_step"] = 0
    memory["progression"]["cycles_without_progress"] = memory["cycles_without_progress"]
    memory["last_verification"] = {
        "status": "continue",
        "reason": reason,
        "next_step": "reanalyze",
    }
    _set_state(memory, STATE_ANALYZE, status="running")
    return memory["cycles_without_progress"] >= MAX_BLOCKED_CYCLES


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _check_output(snapshot: dict[str, Any], tool_name: str) -> Any:
    for check in snapshot.get("checks", []):
        if check.get("tool") != tool_name:
            continue
        result = check.get("result", {})
        if isinstance(result, dict) and result.get("success"):
            return result.get("output")
    return []


def _build_architecture_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    project_types = _as_text_list(_check_output(snapshot, "detect_project_type"))
    repo_tree = _as_text_list(_check_output(snapshot, "scan_repo_tree"))
    entrypoints = _as_text_list(_check_output(snapshot, "find_entrypoints"))

    top_level_directories = sorted(
        {
            item.split("/", 1)[0]
            for item in repo_tree
            if "/" in item and item.split("/", 1)[0]
        }
    )[:20]
    top_level_files = sorted(
        {
            item
            for item in repo_tree
            if "/" not in item
        }
    )[:30]
    important_files = [
        item
        for item in repo_tree
        if item in {"README.md", "Dockerfile", "docker-compose.yml", "requirements.txt", "pyproject.toml"}
        or item.endswith(("/main.py", "/__init__.py"))
    ][:30]

    project_description = ", ".join(project_types) if project_types else "unknown stack"
    entrypoint_description = ", ".join(entrypoints[:5]) if entrypoints else "no entrypoint detected"
    directory_description = ", ".join(top_level_directories[:8]) if top_level_directories else "no top-level directories detected"
    summary = (
        f"Project stack: {project_description}. "
        f"Entrypoints: {entrypoint_description}. "
        f"Main directories: {directory_description}."
    )

    return {
        "summary": summary,
        "languages_frameworks": project_types,
        "entrypoints": entrypoints,
        "top_level_directories": top_level_directories,
        "top_level_files": top_level_files,
        "important_files": important_files,
        "structure_sample": repo_tree[:80],
    }


def _repo_context_text(memory: dict[str, Any]) -> str:
    repo_context = memory.get("repo_context") or {}
    if not isinstance(repo_context, dict):
        repo_context = {}

    payload = {
        "architecture_summary": memory.get("architecture_summary", ""),
        "repo_context": repo_context,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _collaboration_text(memory: dict[str, Any]) -> str:
    payload = {
        "active_agents": memory.get("agents", agent_roster()),
        "orchestrator": build_orchestrator_context(memory),
        "collaboration_summary": memory.get("collaboration_summary", ""),
        "recent_agent_messages": collaboration_context(memory),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _vector_context_text(query: str) -> str:
    try:
        return retrieve_context(query=query, top_k=5)
    except Exception as exc:
        logger.debug("Vector context retrieval failed: %s", exc)
        return "Vector context unavailable."


def _record_agent_message(
    memory: dict[str, Any],
    agent_name: str,
    message: str,
    *,
    phase: str,
    progress_callback: ProgressCallback | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    event = append_agent_message(
        memory,
        agent_name,
        message,
        phase=phase,
        metadata=metadata,
    )
    _emit_progress(
        progress_callback,
        "agent_message",
        f"{agent_name} completed {phase}",
        agent=agent_name,
        phase=phase,
        agent_event=event,
        state=memory.get("state"),
        cycle=memory.get("cycle"),
        step=memory.get("total_steps"),
    )
    try:
        memory["last_agent_history_index"] = index_agent_history(memory)
    except Exception as exc:
        logger.debug("Agent history vector indexing failed: %s", exc)


def _call_agent(
    agent_name: str,
    task_prompt: str,
    memory: dict[str, Any],
    *,
    phase: str,
    progress_callback: ProgressCallback | None = None,
) -> str:
    _emit_progress(
        progress_callback,
        "agent_start",
        f"{agent_name} starting {phase}",
        agent=agent_name,
        phase=phase,
        state=memory.get("state"),
        cycle=memory.get("cycle"),
        step=memory.get("total_steps"),
    )
    expected_agent = select_agent_for_phase(phase)
    assignment = record_assignment(
        memory,
        target_agent=agent_name,
        phase=phase,
        reason=(
            f"orchestrator_agent delegated {phase} to {agent_name}"
            if agent_name == expected_agent
            else f"orchestrator_agent delegated {phase} to {agent_name}; expected {expected_agent}"
        ),
    )
    _emit_progress(
        progress_callback,
        "orchestrator_assignment",
        f"orchestrator_agent assigned {phase} to {agent_name}",
        agent=ORCHESTRATOR_AGENT,
        target_agent=agent_name,
        phase=phase,
        assignment=assignment,
        state=memory.get("state"),
        cycle=memory.get("cycle"),
        step=memory.get("total_steps"),
    )
    output = call_agent(agent_name, task_prompt, collaboration_context(memory))
    record_result(
        memory,
        agent_name=agent_name,
        phase=phase,
        result=_short(output),
        success=not str(output).startswith("[LLM ERROR]"),
    )
    _record_agent_message(
        memory,
        agent_name,
        _short(output),
        phase=phase,
        progress_callback=progress_callback,
    )
    return output


def _refresh_repo_analysis(
    memory: dict[str, Any],
    reason: str,
    progress_callback: ProgressCallback | None = None,
    analysis_type: str = "self_healing",
) -> dict[str, Any]:
    checks = [
        ("detect_project_type", {"root": "."}),
        ("scan_repo_tree", {"root": "."}),
        ("find_entrypoints", {"root": "."}),
    ]
    snapshot = {
        "reason": reason,
        "type": analysis_type,
        "created_at": _now_iso(),
        "checks": [],
    }
    initial_analysis = analysis_type == "initial"

    _emit_progress(
        progress_callback,
        "repo_analysis_start",
        "Analyzing repository architecture"
        if initial_analysis
        else "Refreshing repository analysis after persistent tool failure",
        state=memory.get("state"),
        reason=reason,
        analysis_type=analysis_type,
    )

    for tool_name, tool_args in checks:
        _emit_progress(
            progress_callback,
            "tool_start",
            f"Running repository analysis tool `{tool_name}`",
            tool=tool_name,
            args=tool_args,
            attempt=1,
            max_attempts=1,
            state=memory.get("state"),
            step=memory.get("total_steps"),
            cycle=memory.get("cycle"),
        )
        result = execute_tool(tool_name, tool_args)
        snapshot["checks"].append(
            {
                "tool": tool_name,
                "args": tool_args,
                "result": result,
            }
        )
        _record_event(
            memory=memory,
            step=int(memory.get("total_steps", 0)),
            action="repo_analysis",
            tool=tool_name,
            args=tool_args,
            result=result,
            reason=reason,
            next_step="reanalyze task with refreshed repository context",
            metadata={
                "repo_analysis": True,
                "self_healing": not initial_analysis,
                "analysis_type": analysis_type,
            },
        )
        _emit_progress(
            progress_callback,
            "tool_result" if result.get("success") else "tool_error",
            f"Repository analysis tool `{tool_name}` "
            f"{'succeeded' if result.get('success') else 'failed'}",
            tool=tool_name,
            args=tool_args,
            result=result,
            attempt=1,
            state=memory.get("state"),
            step=memory.get("total_steps"),
            cycle=memory.get("cycle"),
        )

    architecture_context = _build_architecture_context(snapshot)
    snapshot["architecture"] = architecture_context
    snapshot["summary"] = architecture_context["summary"]
    memory["last_repo_analysis"] = snapshot
    memory["repo_context"] = architecture_context
    memory["architecture_summary"] = architecture_context["summary"]
    memory["repo_analysis_round"] = int(memory.get("repo_analysis_round", 0)) + 1
    memory.setdefault("progression", {})
    memory["progression"]["repo_analysis_round"] = memory["repo_analysis_round"]
    memory["progression"]["architecture_summary"] = memory["architecture_summary"]
    memory.setdefault("self_healing", {})
    if not initial_analysis:
        memory["self_healing"]["last_repo_analysis"] = snapshot
    _emit_progress(
        progress_callback,
        "repo_analysis",
        "Repository architecture analyzed" if initial_analysis else "Repository analysis refreshed",
        state=STATE_ANALYZE,
        repo_analysis=snapshot,
        repo_context=architecture_context,
        architecture_summary=architecture_context["summary"],
        analysis_type=analysis_type,
    )
    return snapshot


def _normalize_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    uncertainty = str(analysis.get("uncertainty", "medium")).lower()
    if uncertainty not in {"low", "medium", "high"}:
        uncertainty = "medium"

    key_unknowns = analysis.get("key_unknowns", [])
    if not isinstance(key_unknowns, list):
        key_unknowns = [key_unknowns]

    success_criteria = analysis.get("success_criteria", [])
    if not isinstance(success_criteria, list):
        success_criteria = [success_criteria]

    recommended_actions = analysis.get("recommended_actions", [])
    if not isinstance(recommended_actions, list):
        recommended_actions = [recommended_actions]

    return {
        "summary": str(analysis.get("summary", "")),
        "goal": str(analysis.get("goal", "")),
        "uncertainty": uncertainty,
        "key_unknowns": [str(item) for item in key_unknowns if str(item).strip()],
        "success_criteria": [str(item) for item in success_criteria if str(item).strip()],
        "recommended_actions": [str(item) for item in recommended_actions if str(item).strip()],
        "recommended_focus": str(analysis.get("recommended_focus", "")),
        "next_step": str(analysis.get("next_step", "")),
    }


def _fallback_analysis(task: str, memory: dict[str, Any]) -> dict[str, Any]:
    current_context = get_context_summary(memory)
    repo_context = _repo_context_text(memory)
    return _normalize_analysis(
        {
            "summary": task.strip(),
            "goal": task.strip(),
            "uncertainty": "high" if memory.get("cycle", 1) == 1 else "medium",
            "key_unknowns": [
                "Inspect the repository structure before modifying files.",
                "Identify the safest entrypoints and outputs for the task.",
            ],
            "success_criteria": [
                "The requested task is implemented.",
                "The result is validated through tool execution.",
            ],
            "recommended_actions": [
                "Inspect the repository with read-only tools.",
                "Plan the minimal change set.",
                "Execute and verify incrementally.",
            ],
            "recommended_focus": f"{current_context}\n\nRepository context:\n{repo_context}",
            "next_step": "inspect the repository and form an execution plan",
        }
    )


def _build_analysis_prompt(task: str, memory: dict[str, Any]) -> str:
    context = get_context_summary(memory)
    orchestrator_context = build_orchestrator_context(memory)
    vector_context = _vector_context_text(task)
    return f"""{SYSTEM_PROMPT}

Tu es en phase d'analyse autonome.
Analyse la tâche, le dépôt et le contexte courant avant d'agir.
Tu es orchestrator_agent, cerveau principal du système.

Contrat d'autonomie global:
{AUTONOMY_RULES}

Task utilisateur:
{task}

Cycle actuel:
{memory.get("cycle", 1)}

Contexte courant:
{context}

Contexte orchestrateur:
{orchestrator_context}

Contexte vectoriel pertinent:
{vector_context}

Contexte repository initial:
{_repo_context_text(memory)}

Derniere analyse:
{_short(memory.get("task_analysis"))}

Derniere action:
{_short(memory.get("last_action"))}

Dernier resultat:
{_short(memory.get("last_result"))}

Derniere analyse repo self-healing:
{_short(memory.get("last_repo_analysis"))}

Reponds uniquement en JSON:
{{
  "summary": "...",
  "goal": "...",
  "uncertainty": "low | medium | high",
  "key_unknowns": ["..."],
  "success_criteria": ["..."],
  "recommended_actions": ["..."],
  "recommended_focus": "...",
  "next_step": "..."
}}
"""


def _request_analysis(
    task: str,
    memory: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    raw_output = _call_agent(
        ORCHESTRATOR_AGENT,
        _build_analysis_prompt(task, memory),
        memory,
        phase="analysis",
        progress_callback=progress_callback,
    )
    memory["last_analysis_output"] = raw_output
    parsed = parse_action(raw_output)
    if isinstance(parsed, dict):
        return _normalize_analysis(parsed)

    logger.warning("Analysis JSON invalid, using fallback heuristic analysis")
    return _fallback_analysis(task, memory)


def _build_action_prompt(task: str, memory: dict[str, Any]) -> str:
    state = memory.get("state", STATE_EXECUTE)
    context = get_context_summary(memory)
    task_analysis = _short(memory.get("task_analysis"))
    strategy_change_required = memory.get("strategy_change_required", False)
    blocked_retry = memory.get("blocked_retry") or {}
    vector_context = _vector_context_text(
        " ".join(
            [
                task,
                _short(memory.get("task_analysis"), 500),
                _short(memory.get("last_result"), 500),
            ]
        )
    )
    if state == STATE_FIX and strategy_change_required:
        state_instruction = (
            "La tentative precedente a echoue meme apres auto-correction. "
            "Change de strategie. Ne refais pas le meme appel d'outil avec les memes arguments."
        )
    elif state == STATE_FIX:
        state_instruction = "Corrige l'erreur la plus recente avec un nouvel appel d'outil."
    else:
        state_instruction = "Choisis la prochaine meilleure action pour faire avancer la tache."

    return f"""{SYSTEM_PROMPT}

Mode autonome:
- Etat actuel: {state}
- L'agent ne doit jamais abandonner.
- Si une tentative echoue, il doit corriger puis reessayer.
- N'utilise JAMAIS un tool hors de cette liste.
- Ne demande jamais d'aide humaine, de confirmation ou de clarification.
- Continue jusqu'au succes verifie ou jusqu'au blocage total prouve.
- L'agent est responsable de la reussite finale.

Contrat d'autonomie global:
{AUTONOMY_RULES}

Task utilisateur:
{task}

Plan courant:
{json.dumps(memory.get("plan", []), ensure_ascii=False, indent=2)}

Contexte courant:
{context}

Contexte repository initial:
{_repo_context_text(memory)}

Contexte vectoriel pertinent:
{vector_context}

Contexte collaboration multi-agent:
{_collaboration_text(memory)}

Contexte coder_agent:
{build_coder_context(memory)}

Analyse courante:
{task_analysis}

Cycle d'analyse:
{memory.get("analysis_round", 0)}

Derniere action:
{_short(memory.get("last_action"))}

Dernier resultat:
{_short(memory.get("last_result"))}

Derniere analyse d'erreur tool:
{_short(memory.get("last_tool_analysis"))}

Derniere analyse repo self-healing:
{_short(memory.get("last_repo_analysis"))}

Changement de strategie requis:
{memory.get("strategy_change_required", False)}

Raison du changement de strategie:
{_short(memory.get("strategy_change_reason"))}

Tool a ne pas rejouer tel quel:
{_short(blocked_retry)}

Instruction d'etat:
{state_instruction}

Tools autorises:
{_tool_specs_text()}

Schema de reponse obligatoire:
{{
  "uncertainty": "low | medium | high",
  "intent": "plan | act | fix | final",
  "tool": "tool_name or none",
  "args": {{ ... }},
  "reason": "...",
  "next_action": "what should happen next"
}}

Rappels:
- Commence toujours par choisir un niveau d'incertitude.
- "final" seulement si la tache utilisateur est reellement terminee.
- "fix" ou "act" doivent choisir un tool autorise.
- Si les chemins sont incertains, commence par explorer le depot.
- Si un changement de strategie est requis, choisis une approche differente.
- JSON uniquement.
"""


def _build_evaluate_success_prompt(
    task: str,
    memory: dict[str, Any],
    last_result: dict[str, Any] | None,
) -> str:
    vector_context = _vector_context_text(
        f"{task}\n{_short(last_result, 600)}\n{_short(memory.get('last_validation_report'), 600)}"
    )
    return f"""Tu verifies l'avancement d'un agent autonome.

Contrat d'autonomie global:
{AUTONOMY_RULES}

Task utilisateur:
{task}

Etat actuel:
{memory.get("state")}

Plan courant:
{json.dumps(memory.get("plan", []), ensure_ascii=False, indent=2)}

Analyse courante:
{_short(memory.get("task_analysis"))}

Derniere action:
{_short(memory.get("last_action"))}

Dernier resultat:
{_short(last_result)}

Contexte recent:
{get_context_summary(memory)}

Contexte vectoriel pertinent:
{vector_context}

Contexte reviewer_agent:
{build_reviewer_context(memory)}

Contexte tester_agent:
{build_tester_context(memory)}

Contexte repository initial:
{_repo_context_text(memory)}

Reponds uniquement en JSON:
{{
  "success": true,
  "reason": "...",
}}

Question:
"Est-ce que la tâche est terminée ?"

Regles:
- "success" vaut true seulement si la tache utilisateur est vraiment terminee.
- Si la tache n'est pas terminee, renvoie "success": false avec une raison concise.
- Ne demande jamais une intervention humaine. Si ce n'est pas termine, indique pourquoi continuer.
- Le blocage total doit etre reserve aux cas ou les retries et strategies alternatives sont epuises.
- JSON uniquement.
"""


def _request_action(
    task: str,
    memory: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any] | None:
    raw_output = _call_agent(
        CODER_AGENT,
        _build_action_prompt(task, memory),
        memory,
        phase="action",
        progress_callback=progress_callback,
    )
    memory["last_llm_output"] = raw_output
    parsed = parse_action(raw_output)
    return parsed if isinstance(parsed, dict) else None


def evaluate_success(
    task: str,
    memory: dict[str, Any],
    last_result: dict[str, Any] | None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Ask the LLM whether the task is fully completed."""
    reviewer_output = _call_agent(
        REVIEWER_AGENT,
        _build_evaluate_success_prompt(task, memory, last_result),
        memory,
        phase="review",
        progress_callback=progress_callback,
    )
    tester_output = _call_agent(
        TESTER_AGENT,
        _build_evaluate_success_prompt(task, memory, last_result),
        memory,
        phase="test_verification",
        progress_callback=progress_callback,
    )
    raw_output = reviewer_output
    review_report = normalize_review_report(parse_action(reviewer_output))
    memory["last_review_report"] = review_report
    memory["last_tester_output"] = tester_output
    tester_report = normalize_validation_report(parse_action(tester_output))
    memory["last_validation_report"] = tester_report
    memory["last_evaluate_output"] = raw_output
    parsed = parse_action(raw_output)
    if isinstance(parsed, dict) and "success" in parsed:
        return {
            "success": _coerce_bool(parsed.get("success"), default=False),
            "reason": str(parsed.get("reason", "")),
        }

    return {
        "success": False,
        "reason": f"Invalid success evaluation JSON: {_short(raw_output, 300)}",
    }


def _extract_error_text(result: dict[str, Any]) -> str:
    output = result.get("output")
    if isinstance(output, dict):
        parts = []
        if output.get("type"):
            parts.append(str(output["type"]))
        if output.get("error"):
            parts.append(str(output["error"]))
        if output.get("traceback"):
            parts.append(str(output["traceback"])[:600])
        if parts:
            return " | ".join(parts)
    return _short(output, 800)


def _build_correction_prompt(
    task: str,
    memory: dict[str, Any],
    tool: str,
    args: Any,
    error_text: str,
    retry_number: int,
    failure_history: list[dict[str, Any]],
) -> str:
    max_retries = MAX_SELF_HEALING_RETRIES
    vector_context = _vector_context_text(f"{task}\n{tool}\n{error_text}\n{_short(args, 600)}")
    return f"""{SYSTEM_PROMPT}

Tu fais du self-healing de tool pour un agent autonome.

Contrat d'autonomie global:
{AUTONOMY_RULES}

Task utilisateur:
{task}

Tool en echec:
{tool}

Arguments utilises:
{_short(args)}

Erreur observee:
{error_text}

Retry actuel:
{retry_number}/{max_retries}

Historique des echecs de ce tool:
{json.dumps(failure_history, ensure_ascii=False, indent=2)}

Contexte recent:
{get_context_summary(memory)}

Contexte vectoriel pertinent:
{vector_context}

Contexte debugger_agent:
{build_debugger_context(memory)}

Contexte repository initial:
{_repo_context_text(memory)}

Derniere analyse repo self-healing:
{_short(memory.get("last_repo_analysis"))}

Workflow obligatoire:
1. Analyse l'erreur observee.
2. Genere une correction concrete des arguments.
3. Demande retry=true uniquement si le meme tool peut etre retente de facon utile.
4. Ne change pas de tool ici. Si tu ne peux pas corriger de facon fiable, renvoie retry=false.
5. Ne demande jamais d'aide humaine; transforme l'erreur en prochaine action autonome.

Reponds uniquement en JSON:
{{
  "analysis": "...",
  "retry": true,
  "args": {{ ... }},
  "reason": "..."
}}
"""


def _request_tool_correction(
    task: str,
    memory: dict[str, Any],
    tool: str,
    args: Any,
    error_text: str,
    retry_number: int,
    failure_history: list[dict[str, Any]],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any] | None:
    raw_output = _call_agent(
        DEBUGGER_AGENT,
        _build_correction_prompt(
            task=task,
            memory=memory,
            tool=tool,
            args=args,
            error_text=error_text,
            retry_number=retry_number,
            failure_history=failure_history,
        ),
        memory,
        phase="debug",
        progress_callback=progress_callback,
    )
    memory["last_correction_output"] = raw_output
    parsed = parse_action(raw_output)
    debugger_report = normalize_debugger_report(parsed)
    memory["last_debugger_report"] = debugger_report
    memory.setdefault("debugger_reports", []).append(debugger_report)
    return parsed if isinstance(parsed, dict) else None


def _summarize_collaboration(
    memory: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> None:
    messages = memory.get("agent_messages", [])
    if not isinstance(messages, list) or not messages:
        return

    prompt = f"""Summarize this multi-agent collaboration state for future steps.

Return concise plain text, not JSON.

Current task:
{memory.get("task")}

Recent collaboration:
{collaboration_context(memory, limit=12)}
"""
    summary = _call_agent(
        MEMORY_AGENT,
        prompt,
        memory,
        phase="memory_summary",
        progress_callback=progress_callback,
    )
    memory["collaboration_summary"] = _short(summary, 1200)


def _execute_tool_with_auto_correction(
    task: str,
    memory: dict[str, Any],
    action_type: str,
    tool: str,
    args: Any,
    reason: str,
    next_step: str,
    progress_callback: ProgressCallback | None = None,
) -> tuple[dict[str, Any], bool]:
    current_args = args
    failure_history: list[dict[str, Any]] = []
    max_retries = MAX_SELF_HEALING_RETRIES
    max_attempts = max_retries + 1

    for attempt in range(0, max_attempts):
        retry_number = attempt + 1
        _emit_progress(
            progress_callback,
            "tool_start",
            f"Running tool `{tool}` (attempt {retry_number}/{max_attempts})",
            tool=tool,
            args=current_args,
            attempt=retry_number,
            max_attempts=max_attempts,
            max_retries=max_retries,
            state=memory.get("state"),
            step=memory.get("total_steps"),
        )
        result = execute_tool(tool, current_args)
        error_text = _extract_error_text(result) if not result.get("success") else ""
        retry_reason = reason if attempt == 0 else f"Auto-correction retry #{attempt}: {reason}"

        _record_event(
            memory=memory,
            step=memory["total_steps"],
            action=action_type if attempt == 0 else "auto_retry",
            tool=tool,
            args=current_args,
            result=result,
            reason=retry_reason,
            next_step=next_step,
            metadata={
                "retry_attempt": attempt,
                "retry_number": retry_number,
                "auto_corrected": attempt > 0,
            },
        )

        if result.get("success"):
            memory["strategy_change_required"] = False
            memory["strategy_change_reason"] = ""
            memory["blocked_retry"] = None
            _mark_progress(memory, f"Tool '{tool}' succeeded")
            _emit_progress(
                progress_callback,
                "tool_result",
                f"Tool `{tool}` succeeded",
                tool=tool,
                args=current_args,
                result=result,
                attempt=retry_number,
                state=memory.get("state"),
                step=memory.get("total_steps"),
            )
            if attempt > 0:
                memory.setdefault("self_healing", {})
                memory["self_healing"]["last_success"] = {
                    "tool": tool,
                    "retry_count": attempt,
                    "final_args": current_args,
                    "completed_at": _now_iso(),
                }
                memory["last_tool_analysis"] = {
                    "tool": tool,
                    "analysis": "Auto-correction succeeded",
                    "retry_count": attempt,
                    "final_args": current_args,
                }
            return result, False

        failure_entry = {
            "attempt": retry_number,
            "retry": attempt,
            "args": current_args,
            "error": error_text,
        }
        record_retry(memory, phase="debug", reason=error_text)
        failure_history.append(failure_entry)
        memory["last_tool_analysis"] = {
            "tool": tool,
            "analysis": "Tool execution failed",
            "retry_count": attempt,
            "max_retries": max_retries,
            "last_error": error_text,
            "current_args": current_args,
        }
        _emit_progress(
            progress_callback,
            "tool_error",
            f"Tool `{tool}` failed: {error_text}",
            tool=tool,
            args=current_args,
            result=result,
            error=error_text,
            attempt=retry_number,
            state=memory.get("state"),
            step=memory.get("total_steps"),
        )

        if attempt >= max_retries:
            break

        correction = _request_tool_correction(
            task=task,
            memory=memory,
            tool=tool,
            args=current_args,
            error_text=error_text,
            retry_number=attempt + 1,
            failure_history=failure_history,
            progress_callback=progress_callback,
        )

        if not correction:
            failure_history[-1]["correction_error"] = "Invalid JSON from correction LLM"
            _emit_progress(
                progress_callback,
                "tool_correction_error",
                f"Auto-correction for `{tool}` returned invalid JSON",
                tool=tool,
                error="Invalid JSON from correction LLM",
                attempt=retry_number,
                state=memory.get("state"),
                step=memory.get("total_steps"),
            )
            break

        analysis = str(correction.get("analysis", ""))
        retry = _coerce_bool(correction.get("retry"), default=True)
        corrected_args = correction.get("args")
        correction_reason = str(correction.get("reason", ""))

        failure_history[-1]["analysis"] = analysis
        failure_history[-1]["correction_reason"] = correction_reason

        memory["last_tool_analysis"] = {
            "tool": tool,
            "analysis": analysis,
            "retry": retry,
            "retry_count": attempt + 1,
            "max_retries": max_retries,
            "reason": correction_reason,
            "previous_args": current_args,
            "proposed_args": corrected_args,
        }
        _emit_progress(
            progress_callback,
            "tool_correction",
            f"Auto-correction for `{tool}`: {correction_reason or analysis}",
            tool=tool,
            analysis=analysis,
            retry=retry,
            corrected_args=corrected_args,
            reason=correction_reason,
            attempt=retry_number,
            state=memory.get("state"),
            step=memory.get("total_steps"),
        )

        if not retry or not isinstance(corrected_args, dict):
            failure_history[-1]["correction_error"] = "Correction unavailable or invalid args"
            _emit_progress(
                progress_callback,
                "strategy_change",
                f"Auto-correction cannot continue for `{tool}`. Strategy change required.",
                tool=tool,
                retry=retry,
                corrected_args=corrected_args,
                state=memory.get("state"),
                step=memory.get("total_steps"),
            )
            break

        current_args = corrected_args

    final_error = failure_history[-1]["error"] if failure_history else "Unknown tool failure"
    memory["strategy_change_required"] = True
    memory["strategy_change_reason"] = (
        f"Tool '{tool}' failed after {len(failure_history)} attempt(s) "
        f"and {max_retries} self-healing retry slot(s). Change strategy."
    )
    memory["repo_reanalysis_required"] = True
    memory.setdefault("self_healing", {})
    memory["self_healing"]["persistent_failures"] = (
        int(memory["self_healing"].get("persistent_failures", 0)) + 1
    )
    memory["self_healing"]["last_failure"] = {
        "tool": tool,
        "initial_args": args,
        "last_args": current_args,
        "failure_history": failure_history,
        "failed_at": _now_iso(),
    }
    memory["blocked_retry"] = {
        "tool": tool,
        "initial_args": args,
        "last_args": current_args,
        "failure_history": failure_history,
    }
    memory["last_tool_analysis"] = {
        "tool": tool,
        "analysis": "Auto-correction exhausted",
        "retry_limit": max_retries,
        "failure_history": failure_history,
    }
    _emit_progress(
        progress_callback,
        "strategy_change",
        f"Tool `{tool}` failed after {len(failure_history)} attempt(s). Changing strategy.",
        tool=tool,
        failure_history=failure_history,
        state=memory.get("state"),
        step=memory.get("total_steps"),
    )

    return (
        {
            "success": False,
            "output": {
                "error": final_error,
                "tool": tool,
                "attempts": len(failure_history),
                "retry_limit": max_retries,
                "failure_history": failure_history,
                "strategy_change_required": True,
                "repo_reanalysis_required": True,
            },
        },
        True,
    )


def _verify_result(
    task: str,
    memory: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    last_result = memory.get("last_result")
    if not isinstance(last_result, dict):
        return {
            "status": "fix",
            "reason": "Missing last result",
            "final_result": "",
            "next_step": "retry",
        }

    evaluation = evaluate_success(task, memory, last_result, progress_callback=progress_callback)
    memory["last_success_evaluation"] = evaluation

    if evaluation["success"]:
        return {
            "status": "complete",
            "reason": evaluation["reason"],
            "final_result": memory.get("pending_final") or last_result.get("output", ""),
            "next_step": "",
        }

    if last_result.get("success") is False:
        return {
            "status": "fix",
            "reason": evaluation["reason"] or _short(last_result.get("output")),
            "final_result": "",
            "next_step": "correct the failed tool call",
        }

    return {
        "status": "continue",
        "reason": evaluation["reason"],
        "final_result": "",
        "next_step": "continue working",
    }


def run_agent_loop(
    task: str,
    use_planner: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> Any:
    """Run the autonomous state machine until the task completes."""
    memory = _initial_memory(task, use_planner)
    _set_state(memory, STATE_INIT, status="running")
    _emit_progress(
        progress_callback,
        "run_started",
        f"Starting autonomous run for task: {task}",
        state=STATE_INIT,
        task=task,
    )
    save_memory(memory)

    while True:
        state = memory.get("state", STATE_INIT)
        _emit_progress(
            progress_callback,
            "state",
            f"State: {state} (cycle {memory.get('cycle')}, step {memory.get('step_in_cycle')})",
            state=state,
            cycle=memory.get("cycle"),
            step=memory.get("step_in_cycle"),
            total_steps=memory.get("total_steps"),
        )
        logger.info(
            "Agent state=%s cycle=%s step=%s total_steps=%s",
            state,
            memory.get("cycle"),
            memory.get("step_in_cycle"),
            memory.get("total_steps"),
        )

        if state == STATE_INIT:
            memory["consecutive_failures"] = 0
            memory["pending_final"] = None
            memory["strategy_change_required"] = False
            memory["strategy_change_reason"] = ""
            memory["blocked_retry"] = None
            memory["successful_tools_at_cycle_start"] = int(memory.get("successful_tools", 0))
            memory["cycles_without_progress"] = 0
            memory["blockage_reason"] = ""
            vector_result = execute_tool("index_repository", {"root": ".", "force": False})
            memory["last_vector_index"] = vector_result
            _emit_progress(
                progress_callback,
                "vector_index",
                "Repository vector index refreshed",
                state=STATE_INIT,
                result=vector_result,
            )
            _refresh_repo_analysis(
                memory,
                reason="Initial repository analysis",
                progress_callback=progress_callback,
                analysis_type="initial",
            )
            _set_state(memory, STATE_ANALYZE, status="running")
            _emit_progress(
                progress_callback,
                "transition",
                "Initial repository analysis complete, moving to task analysis",
                state=STATE_ANALYZE,
            )
            save_memory(memory)
            continue

        if state == STATE_ANALYZE:
            analysis = _request_analysis(task, memory)
            memory["task_analysis"] = analysis
            memory["analysis_round"] = int(memory.get("analysis_round", 0)) + 1
            memory["consecutive_failures"] = 0
            memory["repo_reanalysis_required"] = False
            memory.setdefault("progression", {})
            memory["progression"]["analysis_round"] = memory["analysis_round"]
            memory["progression"]["current_step"] = 0
            memory["progression"]["task_analysis"] = analysis
            _emit_progress(
                progress_callback,
                "analysis",
                f"Analysis ready (round {memory['analysis_round']})",
                state=STATE_ANALYZE,
                analysis=analysis,
            )
            _summarize_collaboration(memory, progress_callback=progress_callback)
            _set_state(memory, STATE_PLAN, status="running")
            save_memory(memory)
            continue

        if state == STATE_PLAN:
            try:
                planner_context = get_context_summary(memory)
                planner_context = (
                    f"{planner_context}\n\nContexte repository initial:\n"
                    f"{_repo_context_text(memory)}"
                )
                if memory.get("task_analysis"):
                    planner_context = (
                        f"{planner_context}\n\nAnalyse courante:\n"
                        f"{json.dumps(memory['task_analysis'], ensure_ascii=False, indent=2)}"
                    )
                if use_planner:
                    planner_prompt = f"""Build an execution plan for this task.

Task:
{task}

Context:
{planner_context}

Return a JSON list of objects with step, goal, and tool_hint.
"""
                    raw_plan = _call_agent(
                        PLANNER_AGENT,
                        planner_prompt,
                        memory,
                        phase="planning",
                        progress_callback=progress_callback,
                    )
                    parsed_plan = parse_action(raw_plan)
                    plan = parsed_plan if isinstance(parsed_plan, list) else plan_steps(task, planner_context)
                else:
                    plan = []
                memory["plan"] = plan or []
                memory["consecutive_failures"] = 0
                _emit_progress(
                    progress_callback,
                    "plan",
                    f"Plan ready with {len(memory['plan'])} step(s)",
                    state=STATE_PLAN,
                    plan=memory["plan"],
                )
            except Exception as exc:
                logger.warning("Planner failed: %s", exc)
                memory["plan"] = []
                memory["last_result"] = {"success": False, "output": f"Planner failed: {exc}"}
                memory["consecutive_failures"] = int(memory.get("consecutive_failures", 0)) + 1
                _emit_progress(
                    progress_callback,
                    "plan_error",
                    f"Planner failed: {exc}",
                    state=STATE_PLAN,
                    error=str(exc),
                )
            _set_state(memory, STATE_EXECUTE, status="running")
            save_memory(memory)
            continue

        if state in {STATE_EXECUTE, STATE_FIX}:
            if _soft_limit_reached(memory):
                logger.warning(
                    "Soft limit of %s steps reached in cycle %s, reanalyzing",
                    MAX_STEPS,
                    memory.get("cycle"),
                )
                blocked = _reset_cycle(memory, f"Soft limit {MAX_STEPS} reached, reanalyzing")
                _emit_progress(
                    progress_callback,
                    "cycle_restart",
                    f"Cycle limit reached, restarting cycle {memory.get('cycle')}",
                    state=STATE_ANALYZE,
                    cycle=memory.get("cycle"),
                    max_steps=MAX_STEPS,
                )
                if blocked:
                    return _stop_for_total_blockage(
                        memory,
                        memory.get("blockage_reason", "Total blockage detected"),
                        progress_callback=progress_callback,
                    )
                save_memory(memory)
                continue

            memory["step_in_cycle"] = int(memory.get("step_in_cycle", 0)) + 1
            memory["total_steps"] = int(memory.get("total_steps", 0)) + 1
            memory["progression"]["current_step"] = memory["step_in_cycle"]

            action = _request_action(task, memory, progress_callback=progress_callback)
            if not action:
                result = {
                    "success": False,
                    "output": f"Invalid JSON from LLM: {_short(memory.get('last_llm_output'), 500)}",
                }
                _record_event(
                    memory=memory,
                    step=memory["total_steps"],
                    action="parse_error",
                    tool="parse_action",
                    args={},
                    result=result,
                    reason="LLM action parsing failed",
                    next_step="retry with a stricter prompt",
                )
                memory["last_action"] = None
                memory["last_result"] = result
                memory["consecutive_failures"] = int(memory.get("consecutive_failures", 0)) + 1
                _emit_progress(
                    progress_callback,
                    "llm_parse_error",
                    "LLM action parsing failed, switching to FIX",
                    state=STATE_FIX,
                    result=result,
                )
                _set_state(memory, STATE_FIX, status="running")
                save_memory(memory)
                continue

            action = _normalize_llm_action(action)

            action_type = str(action.get("intent", action.get("action", "act")))
            tool = str(action.get("tool", ""))
            args = action.get("args", {})
            reason = str(action.get("reason", ""))
            next_step = str(action.get("next_action", action.get("next_step", "")))
            uncertainty = str(action.get("uncertainty", "medium"))

            memory["last_action"] = action
            _emit_progress(
                progress_callback,
                "action",
                f"LLM chose action `{action_type}` with tool `{tool or 'none'}`",
                state=state,
                action=action,
                uncertainty=uncertainty,
            )

            if action_type == "plan":
                if isinstance(args, list):
                    memory["plan"] = args
                elif args:
                    memory["plan"] = [args]
                memory["last_result"] = {"success": True, "output": memory["plan"]}
                _emit_progress(
                    progress_callback,
                    "plan",
                    f"LLM updated the plan with {len(memory['plan'])} step(s)",
                    state=STATE_EXECUTE,
                    plan=memory["plan"],
                )
                _set_state(memory, STATE_EXECUTE, status="running")
                save_memory(memory)
                continue

            if action_type == "final" or tool in {"final", "none"}:
                final_output = args.get("result", "") if isinstance(args, dict) else args
                result = {"success": True, "output": final_output}
                _record_event(
                    memory=memory,
                    step=memory["total_steps"],
                    action="final",
                    tool="final",
                    args=args,
                    result=result,
                    reason=reason,
                    next_step=next_step,
                )
                memory["pending_final"] = final_output
                memory["last_result"] = result
                _emit_progress(
                    progress_callback,
                    "intermediate_result",
                    "LLM proposed a final answer, verifying before completion",
                    state=STATE_VERIFY,
                    result=result,
                )
                _set_state(memory, STATE_VERIFY, status="running")
                save_memory(memory)
                continue

            result, change_strategy = _execute_tool_with_auto_correction(
                task=task,
                memory=memory,
                action_type=action_type,
                tool=tool,
                args=args,
                reason=reason,
                next_step=next_step,
                progress_callback=progress_callback,
            )
            memory["last_result"] = result
            if change_strategy:
                memory["pending_final"] = None
                memory["consecutive_failures"] = int(memory.get("consecutive_failures", 0)) + 1
                reason = memory.get("strategy_change_reason") or "Persistent tool failure"
                _refresh_repo_analysis(
                    memory,
                    reason=reason,
                    progress_callback=progress_callback,
                )
                blocked = _reset_cycle(memory, reason)
                _emit_progress(
                    progress_callback,
                    "strategy_change",
                    "Persistent tool failure: strategy changed and repo analysis restarted",
                    state=STATE_ANALYZE,
                    result=result,
                    reason=reason,
                    cycle=memory.get("cycle"),
                )
                if blocked:
                    return _stop_for_total_blockage(
                        memory,
                        memory.get("blockage_reason", "Total blockage detected"),
                        progress_callback=progress_callback,
                    )
            else:
                memory["consecutive_failures"] = 0
                _emit_progress(
                    progress_callback,
                    "intermediate_result",
                    "Tool completed, moving to verification",
                    state=STATE_VERIFY,
                    result=result,
                )
                _set_state(memory, STATE_VERIFY, status="running")
            save_memory(memory)
            continue

        if state == STATE_VERIFY:
            verification = _verify_result(task, memory, progress_callback=progress_callback)
            memory["last_verification"] = verification
            _emit_progress(
                progress_callback,
                "verification",
                f"Verification status: {verification['status']} - {verification['reason']}",
                state=STATE_VERIFY,
                verification=verification,
            )

            if verification["status"] == "complete":
                final_output = (
                    verification.get("final_result")
                    or memory.get("pending_final")
                    or memory.get("last_result", {}).get("output", "")
                )
                memory["final_result"] = final_output
                memory["completed_at"] = _now_iso()
                _mark_progress(memory, "Task completed")
                _set_state(memory, STATE_COMPLETE, status="completed")
                _emit_progress(
                    progress_callback,
                    "complete",
                    "Task completed successfully",
                    state=STATE_COMPLETE,
                    final_result=final_output,
                )
                save_memory(memory)
                continue

            if verification["status"] == "fix":
                memory["pending_final"] = None
                memory["consecutive_failures"] = int(memory.get("consecutive_failures", 0)) + 1
                if memory["consecutive_failures"] > MAX_RETRIES:
                    logger.warning(
                        "Too many consecutive failures (%s), forcing reanalysis",
                        memory["consecutive_failures"],
                    )
                    memory["consecutive_failures"] = 0
                    _emit_progress(
                        progress_callback,
                        "cycle_restart",
                        "Too many verification failures, reanalyzing automatically",
                        state=STATE_ANALYZE,
                        verification=verification,
                    )
                    _set_state(memory, STATE_ANALYZE, status="running")
                else:
                    _emit_progress(
                        progress_callback,
                        "transition",
                        "Verification requested a fix",
                        state=STATE_FIX,
                        verification=verification,
                    )
                    _set_state(memory, STATE_FIX, status="running")
                save_memory(memory)
                continue

            memory["pending_final"] = None
            memory["consecutive_failures"] = 0
            blocked = _reset_cycle(memory, verification["reason"] or "Task not completed yet")
            _emit_progress(
                progress_callback,
                "cycle_restart",
                "Task not complete yet, relaunching a new cycle automatically",
                state=STATE_ANALYZE,
                verification=verification,
                cycle=memory.get("cycle"),
            )
            if blocked:
                return _stop_for_total_blockage(
                    memory,
                    memory.get("blockage_reason", "Total blockage detected"),
                    progress_callback=progress_callback,
                )
            save_memory(memory)
            continue

        if state == STATE_COMPLETE:
            save_memory(memory)
            _emit_progress(
                progress_callback,
                "run_finished",
                "Run finished",
                state=STATE_COMPLETE,
                final_result=memory.get("final_result", ""),
                status=memory.get("status"),
            )
            return memory.get("final_result", "")

        logger.warning("Unknown state '%s', reinitializing analysis", state)
        _emit_progress(
            progress_callback,
            "transition",
            f"Unknown state `{state}`, returning to analysis",
            state=STATE_ANALYZE,
        )
        _set_state(memory, STATE_ANALYZE, status="running")
        save_memory(memory)


__all__ = [
    "MAX_STEPS",
    "MAX_SELF_HEALING_RETRIES",
    "STATE_COMPLETE",
    "STATE_ANALYZE",
    "STATE_EXECUTE",
    "STATE_FIX",
    "STATE_INIT",
    "STATE_PLAN",
    "STATE_VERIFY",
    "run_agent_loop",
]
