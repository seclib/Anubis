import json
import unittest
from unittest.mock import patch

from agent import loop
from agent.coder_agent import (
    CODER_PROMPT,
    CODER_RESPONSIBILITIES,
    CODER_RULES,
    RECOMMENDED_CODER_MODEL,
    build_coder_context,
)
from agent.orchestrator_agent import (
    ORCHESTRATOR_RESPONSIBILITIES,
    aggregate_results,
    priority_for_phase,
    record_assignment,
    record_result,
)
from agent.prompts import AUTONOMY_RULES, SYSTEM_PROMPT
from agent.streaming import agent_event_payload, format_progress_event, format_sse_event
from agent.tester_agent import (
    TESTER_PROMPT,
    TESTER_REPORT_SCHEMA,
    TESTER_RESPONSIBILITIES,
    TESTER_RULES,
    build_tester_context,
    normalize_validation_report,
)


class AutonomousLoopTest(unittest.TestCase):
    def _fake_call_agent(self, fake_llm):
        def call_agent(agent_name: str, prompt: str, collaboration_context: str = "") -> str:
            if agent_name == loop.PLANNER_AGENT:
                return json.dumps([{"step": 1, "goal": "Plan", "tool_hint": "read_file"}])
            if agent_name == loop.MEMORY_AGENT:
                return "collaboration summary"
            if agent_name == loop.TESTER_AGENT:
                return json.dumps(
                    {
                        "success": False,
                        "status": "failed",
                        "summary": "tester evidence recorded",
                        "commands": ["python3 -m unittest"],
                        "errors": [
                            {
                                "type": "runtime",
                                "message": "boom",
                                "command": "python3 -m unittest",
                                "evidence": "Traceback",
                            }
                        ],
                        "next_action": "fix",
                    }
                )
            return fake_llm(prompt)

        return call_agent

    def test_global_autonomy_contract_is_in_all_llm_prompts(self):
        memory = loop._initial_memory("Fix the project", use_planner=True)
        memory["last_result"] = {"success": False, "output": "boom"}

        prompts = [
            SYSTEM_PROMPT,
            loop._build_analysis_prompt("Fix the project", memory),
            loop._build_action_prompt("Fix the project", memory),
            loop._build_evaluate_success_prompt("Fix the project", memory, memory["last_result"]),
            loop._build_correction_prompt(
                task="Fix the project",
                memory=memory,
                tool="read_file",
                args={"path": "missing.md"},
                error_text="Missing file",
                retry_number=1,
                failure_history=[],
            ),
        ]

        for prompt in prompts:
            self.assertIn(AUTONOMY_RULES, prompt)
            self.assertIn("Never ask for human help", prompt)
            self.assertIn("You are responsible for the final success", prompt)

    def test_multi_agent_roster_contains_dedicated_roles_and_models(self):
        memory = loop._initial_memory("Build multi-agent system", use_planner=True)
        roster = {agent["name"]: agent for agent in memory["agents"]}

        expected_agents = {
            loop.ORCHESTRATOR_AGENT,
            loop.PLANNER_AGENT,
            loop.CODER_AGENT,
            loop.REVIEWER_AGENT,
            loop.TESTER_AGENT,
            loop.DEBUGGER_AGENT,
            loop.MEMORY_AGENT,
        }

        self.assertEqual(set(roster), expected_agents)
        for agent in roster.values():
            self.assertTrue(agent["role"])
            self.assertTrue(agent["model"])
            self.assertTrue(agent["prompt"])

    def test_orchestrator_agent_owns_distribution_priorities_and_aggregation(self):
        memory = loop._initial_memory("Ship feature", use_planner=True)
        orchestration = memory["orchestration"]

        self.assertEqual(orchestration["agent"], loop.ORCHESTRATOR_AGENT)
        self.assertEqual(orchestration["responsibilities"], ORCHESTRATOR_RESPONSIBILITIES)
        self.assertGreater(priority_for_phase("debug"), priority_for_phase("memory_summary"))

        assignment = record_assignment(
            memory,
            target_agent=loop.CODER_AGENT,
            phase="action",
            reason="implement next step",
        )
        record_result(
            memory,
            agent_name=loop.CODER_AGENT,
            phase="action",
            result="implemented",
            success=True,
        )

        self.assertEqual(assignment["from"], loop.ORCHESTRATOR_AGENT)
        self.assertEqual(assignment["to"], loop.CODER_AGENT)
        self.assertEqual(memory["orchestration"]["current_assignment"], assignment)
        self.assertIn("coder_agent [action] success=True", aggregate_results(memory))

    def test_coder_agent_contract_uses_recommended_model_and_minimal_rules(self):
        memory = loop._initial_memory("Implement feature", use_planner=True)
        roster = {agent["name"]: agent for agent in memory["agents"]}
        coder = roster[loop.CODER_AGENT]

        self.assertEqual(coder["model"], RECOMMENDED_CODER_MODEL)
        self.assertEqual(memory["coder_agent"]["responsibilities"], CODER_RESPONSIBILITIES)
        self.assertIn("modify_code", CODER_RESPONSIBILITIES)
        self.assertIn("create_files", CODER_RESPONSIBILITIES)
        self.assertIn("refactor_existing_code", CODER_RESPONSIBILITIES)
        self.assertIn("implement_features", CODER_RESPONSIBILITIES)
        self.assertIn("produce minimal clean code", CODER_RULES)
        self.assertIn("respect the existing architecture", CODER_RULES)
        self.assertIn("avoid unnecessary changes", CODER_RULES)
        self.assertEqual(coder["prompt"], CODER_PROMPT)
        self.assertIn(RECOMMENDED_CODER_MODEL, build_coder_context(memory))

    def test_tester_agent_contract_returns_structured_validation_report(self):
        memory = loop._initial_memory("Validate feature", use_planner=True)
        roster = {agent["name"]: agent for agent in memory["agents"]}
        tester = roster[loop.TESTER_AGENT]

        self.assertEqual(memory["tester_agent"]["responsibilities"], TESTER_RESPONSIBILITIES)
        self.assertIn("execute_tests", TESTER_RESPONSIBILITIES)
        self.assertIn("run_validation_commands", TESTER_RESPONSIBILITIES)
        self.assertIn("detect_runtime_errors", TESTER_RESPONSIBILITIES)
        self.assertIn("verify_results", TESTER_RESPONSIBILITIES)
        self.assertIn("analyze shell outputs", TESTER_RULES)
        self.assertIn("return structured errors", TESTER_RULES)
        self.assertIn("generate validation reports", TESTER_RULES)
        self.assertEqual(tester["prompt"], TESTER_PROMPT)
        self.assertIn("Validation report schema", build_tester_context(memory))

        report = normalize_validation_report(
            {
                "success": False,
                "status": "failed",
                "summary": "runtime failure",
                "commands": "python app.py",
                "errors": "RuntimeError",
                "next_action": "fix",
            }
        )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["commands"], ["python app.py"])
        self.assertEqual(report["errors"][0]["type"], "unknown")
        self.assertEqual(TESTER_REPORT_SCHEMA["success"], "boolean")

    def test_loop_reanalyzes_until_completion_without_human_stop(self):
        events = []
        analysis_count = 0
        action_count = 0
        verification_count = 0
        soft_limit_count = 0

        def fake_llm(prompt: str) -> str:
            nonlocal analysis_count, action_count, verification_count

            if "Tu es en phase d'analyse autonome." in prompt:
                analysis_count += 1
                return json.dumps(
                    {
                        "summary": "Analyse du dépôt",
                        "goal": "Rendre la boucle autonome",
                        "uncertainty": "medium",
                        "key_unknowns": ["Structure du dépôt", "Flux d'exécution"],
                        "success_criteria": [
                            "Le cycle repart par analyse",
                            "La tâche finit sans arrêt prématuré",
                        ],
                        "recommended_actions": ["Analyser", "Planifier", "Exécuter", "Vérifier"],
                        "recommended_focus": "Boucle autonome",
                        "next_step": "planifier",
                    }
                )

            if "Tu verifies l'avancement d'un agent autonome." in prompt:
                verification_count += 1
                return json.dumps(
                    {
                        "success": verification_count >= 2,
                        "reason": "continue" if verification_count == 1 else "complete",
                    }
                )

            if "Schema de reponse obligatoire" in prompt:
                action_count += 1
                if action_count == 1:
                    return json.dumps(
                        {
                            "uncertainty": "low",
                            "intent": "act",
                            "tool": "read_file",
                            "args": {"path": "README.md"},
                            "reason": "Inspecter le dépôt",
                            "next_action": "verifier",
                        }
                    )

                return json.dumps(
                    {
                        "uncertainty": "low",
                        "intent": "final",
                        "tool": "final",
                        "args": {"result": "done"},
                        "reason": "Terminé",
                        "next_action": "",
                    }
                )

            raise AssertionError(f"Unexpected prompt: {prompt[:200]}")

        def fake_soft_limit(memory: dict[str, object]) -> bool:
            nonlocal soft_limit_count
            soft_limit_count += 1
            return soft_limit_count == 1

        with (
            patch.object(loop, "call_agent", side_effect=self._fake_call_agent(fake_llm)),
            patch.object(loop, "load_memory", return_value={}),
            patch.object(loop, "save_memory", lambda memory: None),
            patch.object(loop, "append_event", lambda memory, event: None),
            patch.object(
                loop,
                "plan_steps",
                return_value=[{"step": 1, "goal": "Inspect", "tool_hint": "read_file"}],
            ),
            patch.object(loop, "execute_tool", return_value={"success": True, "output": "ok"}),
            patch.object(loop, "get_context_summary", return_value="context"),
            patch.object(loop, "_soft_limit_reached", side_effect=fake_soft_limit),
            patch.object(loop, "CONTINUOUS_RUN", False),
        ):
            result = loop.run_agent_loop(
                "Improve autonomy",
                use_planner=True,
                progress_callback=events.append,
            )

        self.assertEqual(result, "done")
        self.assertEqual(analysis_count, 3)
        self.assertEqual(action_count, 2)
        self.assertEqual(verification_count, 2)
        self.assertTrue(
            any(event["type"] == "cycle_restart" and event.get("state") == loop.STATE_ANALYZE for event in events)
        )
        self.assertTrue(any(event["type"] == "analysis" for event in events))

    def test_tool_self_healing_retries_then_restarts_repo_analysis(self):
        events = []
        llm_prompts = []
        analysis_prompts = []
        analysis_count = 0
        action_count = 0
        correction_count = 0
        verification_count = 0
        tool_calls = []

        def fake_llm(prompt: str) -> str:
            nonlocal analysis_count, action_count, correction_count, verification_count
            llm_prompts.append(prompt)

            if "Tu es en phase d'analyse autonome." in prompt:
                analysis_count += 1
                analysis_prompts.append(prompt)
                return json.dumps(
                    {
                        "summary": "Analyse self-healing",
                        "goal": "Corriger puis changer de strategie",
                        "uncertainty": "medium",
                        "key_unknowns": ["Erreur tool"],
                        "success_criteria": ["Retry limite", "Analyse repo relancee"],
                        "recommended_actions": ["Corriger", "Relancer analyse"],
                        "recommended_focus": "Self-healing",
                        "next_step": "executer",
                    }
                )

            if "Tu fais du self-healing de tool" in prompt:
                correction_count += 1
                return json.dumps(
                    {
                        "analysis": f"Correction {correction_count}",
                        "retry": True,
                        "args": {"path": f"missing-{correction_count}.md"},
                        "reason": "Retenter avec un chemin corrige",
                    }
                )

            if "Tu verifies l'avancement d'un agent autonome." in prompt:
                verification_count += 1
                return json.dumps({"success": True, "reason": "complete"})

            if "Schema de reponse obligatoire" in prompt:
                action_count += 1
                if action_count == 1:
                    return json.dumps(
                        {
                            "uncertainty": "low",
                            "intent": "act",
                            "tool": "read_file",
                            "args": {"path": "missing.md"},
                            "reason": "Lire le fichier cible",
                            "next_action": "verifier",
                        }
                    )

                return json.dumps(
                    {
                        "uncertainty": "low",
                        "intent": "final",
                        "tool": "final",
                        "args": {"result": "done"},
                        "reason": "Strategie corrigee",
                        "next_action": "",
                    }
                )

            raise AssertionError(f"Unexpected prompt: {prompt[:200]}")

        def fake_execute_tool(tool: str, args: dict[str, object] | None = None) -> dict[str, object]:
            tool_calls.append((tool, args or {}))
            if tool == "read_file":
                return {
                    "success": False,
                    "output": {
                        "type": "FileNotFoundError",
                        "error": f"Missing file: {(args or {}).get('path')}",
                    },
                }

            return {"success": True, "output": [f"{tool}:ok"]}

        with (
            patch.object(loop, "call_agent", side_effect=self._fake_call_agent(fake_llm)),
            patch.object(loop, "load_memory", return_value={}),
            patch.object(loop, "save_memory", lambda memory: None),
            patch.object(loop, "append_event", lambda memory, event: None),
            patch.object(
                loop,
                "plan_steps",
                return_value=[{"step": 1, "goal": "Read file", "tool_hint": "read_file"}],
            ),
            patch.object(loop, "execute_tool", side_effect=fake_execute_tool),
            patch.object(loop, "get_context_summary", return_value="context"),
        ):
            result = loop.run_agent_loop(
                "Exercise self-healing",
                use_planner=True,
                progress_callback=events.append,
            )

        self.assertEqual(result, "done")
        self.assertEqual(correction_count, 3)
        self.assertEqual([tool for tool, _ in tool_calls].count("read_file"), 4)
        self.assertIn("detect_project_type", [tool for tool, _ in tool_calls])
        self.assertIn("scan_repo_tree", [tool for tool, _ in tool_calls])
        self.assertIn("find_entrypoints", [tool for tool, _ in tool_calls])
        self.assertEqual(analysis_count, 2)
        self.assertEqual(action_count, 2)
        self.assertEqual(verification_count, 1)
        self.assertTrue(all("Contexte repository initial" in prompt for prompt in llm_prompts))
        self.assertIn("detect_project_type:ok", analysis_prompts[0])
        self.assertTrue(
            any(
                event["type"] == "repo_analysis"
                and event.get("analysis_type") == "initial"
                for event in events
            )
        )
        self.assertIn("Derniere analyse repo self-healing", analysis_prompts[-1])
        self.assertTrue(any(event["type"] == "repo_analysis" for event in events))
        self.assertTrue(
            any(event["type"] == "strategy_change" and event.get("state") == loop.STATE_ANALYZE for event in events)
        )

    def test_initial_repo_analysis_streams_each_tool(self):
        events = []

        def fake_llm(prompt: str) -> str:
            if "Tu es en phase d'analyse autonome." in prompt:
                return json.dumps(
                    {
                        "summary": "Analyse",
                        "goal": "Terminer",
                        "uncertainty": "low",
                        "key_unknowns": [],
                        "success_criteria": ["done"],
                        "recommended_actions": ["final"],
                        "recommended_focus": "final",
                        "next_step": "final",
                    }
                )

            if "Tu verifies l'avancement d'un agent autonome." in prompt:
                return json.dumps({"success": True, "reason": "complete"})

            if "Schema de reponse obligatoire" in prompt:
                return json.dumps(
                    {
                        "uncertainty": "low",
                        "intent": "final",
                        "tool": "final",
                        "args": {"result": "done"},
                        "reason": "Terminé",
                        "next_action": "",
                    }
                )

            raise AssertionError(f"Unexpected prompt: {prompt[:200]}")

        with (
            patch.object(loop, "call_agent", side_effect=self._fake_call_agent(fake_llm)),
            patch.object(loop, "load_memory", return_value={}),
            patch.object(loop, "save_memory", lambda memory: None),
            patch.object(loop, "append_event", lambda memory, event: None),
            patch.object(loop, "plan_steps", return_value=[]),
            patch.object(loop, "execute_tool", return_value={"success": True, "output": ["ok"]}),
            patch.object(loop, "get_context_summary", return_value="context"),
        ):
            result = loop.run_agent_loop("Stream repo tools", progress_callback=events.append)

        self.assertEqual(result, "done")
        repo_tools = {"detect_project_type", "scan_repo_tree", "find_entrypoints"}
        started = {
            event.get("tool")
            for event in events
            if event["type"] == "tool_start" and event.get("tool") in repo_tools
        }
        finished = {
            event.get("tool")
            for event in events
            if event["type"] == "tool_result" and event.get("tool") in repo_tools
        }
        self.assertEqual(started, repo_tools)
        self.assertEqual(finished, repo_tools)

    def test_structured_stream_payload_contains_tool_result_and_progress(self):
        event = {
            "type": "tool_result",
            "message": "Tool `read_file` succeeded",
            "state": loop.STATE_EXECUTE,
            "tool": "read_file",
            "step": 2,
            "cycle": 1,
            "result": {"success": True, "output": "hello"},
        }

        payload = agent_event_payload(event, sequence=7)
        text = format_progress_event(event)
        sse = format_sse_event("agent_progress", payload, event_id=7)

        self.assertEqual(payload["sequence"], 7)
        self.assertEqual(payload["progress"]["state"], loop.STATE_EXECUTE)
        self.assertIn("hello", payload["result_summary"])
        self.assertIn("[TOOL_RESULT]", text)
        self.assertIn("tool=read_file", text)
        self.assertIn("event: agent_progress", sse)
        self.assertIn('"sequence": 7', sse)


if __name__ == "__main__":
    unittest.main()
