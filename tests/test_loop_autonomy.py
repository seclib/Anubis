import json
import unittest
from unittest.mock import patch

from agent import loop


class AutonomousLoopTest(unittest.TestCase):
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
            patch.object(loop, "call_llm", side_effect=fake_llm),
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
            patch.object(loop, "call_llm", side_effect=fake_llm),
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


if __name__ == "__main__":
    unittest.main()
