"""Autonomous agent loop with an explicit state machine."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from agent.memory import append_event, get_context_summary, load_memory, save_memory
from agent.parser import parse_action
from agent.planner import plan_steps
from agent.prompts import SYSTEM_PROMPT
from config import CONTINUOUS_RUN, MAX_RETRIES, MAX_STEPS as CONFIG_MAX_STEPS, MAX_TOOL_RETRIES
from executor.tool_executor import execute_tool
from llm.ollama import call_llm

logger = logging.getLogger(__name__)

MAX_STEPS = CONFIG_MAX_STEPS
MAX_BLOCKED_CYCLES = 3

STATE_INIT = "INIT"
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
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    return text[:limit]


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
        "status": "running",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "completed_at": None,
        "max_steps": MAX_STEPS,
        "continuous_run": CONTINUOUS_RUN,
        "use_planner": use_planner,
        "state": STATE_INIT,
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
        "strategy_change_required": False,
        "strategy_change_reason": "",
        "blocked_retry": None,
        "last_tool_analysis": None,
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
        "next_step": "replan",
    }
    _set_state(memory, STATE_PLAN, status="running")
    return memory["cycles_without_progress"] >= MAX_BLOCKED_CYCLES


def _build_action_prompt(task: str, memory: dict[str, Any]) -> str:
    state = memory.get("state", STATE_EXECUTE)
    context = get_context_summary(memory)
    strategy_change_required = memory.get("strategy_change_required", False)
    blocked_retry = memory.get("blocked_retry") or {}
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

Task utilisateur:
{task}

Plan courant:
{json.dumps(memory.get("plan", []), ensure_ascii=False, indent=2)}

Contexte courant:
{context}

Derniere action:
{_short(memory.get("last_action"))}

Dernier resultat:
{_short(memory.get("last_result"))}

Derniere analyse d'erreur tool:
{_short(memory.get("last_tool_analysis"))}

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
    return f"""Tu verifies l'avancement d'un agent autonome.

Task utilisateur:
{task}

Etat actuel:
{memory.get("state")}

Plan courant:
{json.dumps(memory.get("plan", []), ensure_ascii=False, indent=2)}

Derniere action:
{_short(memory.get("last_action"))}

Dernier resultat:
{_short(last_result)}

Contexte recent:
{get_context_summary(memory)}

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
- JSON uniquement.
"""


def _request_action(task: str, memory: dict[str, Any]) -> dict[str, Any] | None:
    raw_output = call_llm(_build_action_prompt(task, memory))
    memory["last_llm_output"] = raw_output
    parsed = parse_action(raw_output)
    return parsed if isinstance(parsed, dict) else None


def evaluate_success(
    task: str,
    memory: dict[str, Any],
    last_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Ask the LLM whether the task is fully completed."""
    raw_output = call_llm(_build_evaluate_success_prompt(task, memory, last_result))
    memory["last_evaluate_output"] = raw_output
    parsed = parse_action(raw_output)
    if isinstance(parsed, dict) and "success" in parsed:
        return {
            "success": bool(parsed.get("success")),
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
    return f"""{SYSTEM_PROMPT}

Tu fais de l'auto-correction de tool pour un agent autonome.

Task utilisateur:
{task}

Tool en echec:
{tool}

Arguments utilises:
{_short(args)}

Erreur observee:
{error_text}

Retry actuel:
{retry_number}/{MAX_TOOL_RETRIES}

Historique des echecs de ce tool:
{json.dumps(failure_history, ensure_ascii=False, indent=2)}

Contexte recent:
{get_context_summary(memory)}

Analyse l'erreur puis propose des arguments corriges pour RETENTER LE MEME TOOL.
Ne change pas de tool ici. Si tu ne peux pas corriger de facon fiable, renvoie retry=false.

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
) -> dict[str, Any] | None:
    raw_output = call_llm(
        _build_correction_prompt(
            task=task,
            memory=memory,
            tool=tool,
            args=args,
            error_text=error_text,
            retry_number=retry_number,
            failure_history=failure_history,
        )
    )
    memory["last_correction_output"] = raw_output
    parsed = parse_action(raw_output)
    return parsed if isinstance(parsed, dict) else None


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

    for attempt in range(0, MAX_TOOL_RETRIES + 1):
        retry_number = attempt + 1
        _emit_progress(
            progress_callback,
            "tool_start",
            f"Running tool `{tool}` (attempt {retry_number}/{MAX_TOOL_RETRIES + 1})",
            tool=tool,
            args=current_args,
            attempt=retry_number,
            max_attempts=MAX_TOOL_RETRIES + 1,
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
                memory["last_tool_analysis"] = {
                    "tool": tool,
                    "analysis": "Auto-correction succeeded",
                    "retry_count": attempt,
                    "final_args": current_args,
                }
            return result, False

        failure_entry = {
            "attempt": retry_number,
            "args": current_args,
            "error": error_text,
        }
        failure_history.append(failure_entry)
        memory["last_tool_analysis"] = {
            "tool": tool,
            "analysis": "Tool execution failed",
            "retry_count": attempt,
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

        if attempt >= MAX_TOOL_RETRIES:
            break

        correction = _request_tool_correction(
            task=task,
            memory=memory,
            tool=tool,
            args=current_args,
            error_text=error_text,
            retry_number=attempt + 1,
            failure_history=failure_history,
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
        retry = bool(correction.get("retry", True))
        corrected_args = correction.get("args")
        correction_reason = str(correction.get("reason", ""))

        failure_history[-1]["analysis"] = analysis
        failure_history[-1]["correction_reason"] = correction_reason

        memory["last_tool_analysis"] = {
            "tool": tool,
            "analysis": analysis,
            "retry": retry,
            "retry_count": attempt + 1,
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
        f"Tool '{tool}' failed after {len(failure_history)} attempts. Change strategy."
    )
    memory["blocked_retry"] = {
        "tool": tool,
        "initial_args": args,
        "last_args": current_args,
        "failure_history": failure_history,
    }
    memory["last_tool_analysis"] = {
        "tool": tool,
        "analysis": "Auto-correction exhausted",
        "retry_limit": MAX_TOOL_RETRIES,
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
                "failure_history": failure_history,
                "strategy_change_required": True,
            },
        },
        True,
    )


def _verify_result(task: str, memory: dict[str, Any]) -> dict[str, Any]:
    last_result = memory.get("last_result")
    if not isinstance(last_result, dict):
        return {
            "status": "fix",
            "reason": "Missing last result",
            "final_result": "",
            "next_step": "retry",
        }

    evaluation = evaluate_success(task, memory, last_result)
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
            _set_state(memory, STATE_PLAN, status="running")
            _emit_progress(
                progress_callback,
                "transition",
                "Initializing run and moving to planning",
                state=STATE_PLAN,
            )
            save_memory(memory)
            continue

        if state == STATE_PLAN:
            try:
                plan = plan_steps(task, get_context_summary(memory)) if use_planner else []
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
                if memory.get("continuous_run", True):
                    logger.warning(
                        "Soft limit of %s steps reached in cycle %s, replanning",
                        MAX_STEPS,
                        memory.get("cycle"),
                    )
                    _emit_progress(
                        progress_callback,
                        "cycle_restart",
                        f"Cycle limit reached, restarting cycle {memory.get('cycle') + 1}",
                        state=state,
                        cycle=memory.get("cycle"),
                        max_steps=MAX_STEPS,
                    )
                    blocked = _reset_cycle(memory, f"Soft limit {MAX_STEPS} reached, replanning")
                    if blocked:
                        return _stop_for_total_blockage(
                            memory,
                            memory.get("blockage_reason", "Total blockage detected"),
                            progress_callback=progress_callback,
                        )
                    save_memory(memory)
                    continue

                memory["status"] = "max_steps_reached"
                memory["completed_at"] = _now_iso()
                save_memory(memory)
                return {
                    "status": "max_steps_reached",
                    "task": task,
                    "steps": len(memory.get("steps", [])),
                    "last_result": memory.get("last_result"),
                }

            memory["step_in_cycle"] = int(memory.get("step_in_cycle", 0)) + 1
            memory["total_steps"] = int(memory.get("total_steps", 0)) + 1
            memory["progression"]["current_step"] = memory["step_in_cycle"]

            action = _request_action(task, memory)
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
                if memory["consecutive_failures"] > MAX_RETRIES:
                    logger.warning(
                        "Too many consecutive strategy failures (%s), replanning",
                        memory["consecutive_failures"],
                    )
                    memory["consecutive_failures"] = 0
                    _emit_progress(
                        progress_callback,
                        "cycle_restart",
                        "Too many strategy failures, replanning automatically",
                        state=STATE_PLAN,
                        result=result,
                    )
                    _set_state(memory, STATE_PLAN, status="running")
                else:
                    _emit_progress(
                        progress_callback,
                        "transition",
                        "Tool failed after retries, switching to FIX",
                        state=STATE_FIX,
                        result=result,
                    )
                    _set_state(memory, STATE_FIX, status="running")
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
            verification = _verify_result(task, memory)
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
                        "Too many consecutive failures (%s), forcing replan",
                        memory["consecutive_failures"],
                    )
                    memory["consecutive_failures"] = 0
                    _emit_progress(
                        progress_callback,
                        "cycle_restart",
                        "Too many verification failures, replanning automatically",
                        state=STATE_PLAN,
                        verification=verification,
                    )
                    _set_state(memory, STATE_PLAN, status="running")
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
            if memory.get("continuous_run", True):
                _emit_progress(
                    progress_callback,
                    "cycle_restart",
                    "Task not complete yet, relaunching a new cycle automatically",
                    state=STATE_PLAN,
                    verification=verification,
                )
                blocked = _reset_cycle(memory, verification["reason"] or "Task not completed yet")
                if blocked:
                    return _stop_for_total_blockage(
                        memory,
                        memory.get("blockage_reason", "Total blockage detected"),
                        progress_callback=progress_callback,
                    )
            else:
                _set_state(memory, STATE_PLAN, status="running")
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

        logger.warning("Unknown state '%s', reinitializing planner", state)
        _emit_progress(
            progress_callback,
            "transition",
            f"Unknown state `{state}`, returning to planning",
            state=STATE_PLAN,
        )
        _set_state(memory, STATE_PLAN, status="running")
        save_memory(memory)


__all__ = [
    "MAX_STEPS",
    "STATE_COMPLETE",
    "STATE_EXECUTE",
    "STATE_FIX",
    "STATE_INIT",
    "STATE_PLAN",
    "STATE_VERIFY",
    "run_agent_loop",
]
