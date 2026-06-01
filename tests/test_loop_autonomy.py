import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import loop
from memory import hermes as hermes_memory
from memory import query_cache
from memory import vector as vector_memory
from agent.communication import (
    communication_context,
    communication_snapshot,
    dequeue_agent_messages,
    enqueue_agent_message,
)
from agent.self_improvement import (
    analyze_performance,
    optimize_prompt_guidance,
    propose_strategy_improvements,
    update_self_improvement_memory,
)
from runtime import tool_registry as tool_executor
from tools import autonomous_developer
from tools import git_autonomy
from tools import dynamic_tools
from tools import hermes_memory as hermes_tools
from tools.sandbox import SandboxViolation, audit_tool_action, validate_command
from tools.terminal import run_command
from agent.coder_agent import (
    CODER_PROMPT,
    CODER_RESPONSIBILITIES,
    CODER_RULES,
    RECOMMENDED_CODER_MODEL,
    build_coder_context,
)
from agent.debugger_agent import (
    DEBUGGER_PROMPT,
    DEBUGGER_REPORT_SCHEMA,
    DEBUGGER_RESPONSIBILITIES,
    DEBUGGER_RULES,
    build_debugger_context,
    normalize_debugger_report,
)
from agent.orchestrator_agent import (
    ORCHESTRATOR_RESPONSIBILITIES,
    aggregate_results,
    build_parallel_batches,
    build_priority_plan,
    priority_for_phase,
    record_assignment,
    record_result,
    update_priority_engine,
)
from agent.prompts import AUTONOMY_RULES, SYSTEM_PROMPT
from agent.reviewer_agent import (
    REVIEWER_PROMPT,
    REVIEWER_RESPONSIBILITIES,
    REVIEWER_RULES,
    REVIEW_REPORT_SCHEMA,
    build_reviewer_context,
    normalize_review_report,
)
from agent.streaming import (
    agent_event_payload,
    format_live_execution_event,
    format_progress_event,
    format_sse_event,
)
from agent.tester_agent import (
    TESTER_PROMPT,
    TESTER_REPORT_SCHEMA,
    TESTER_RESPONSIBILITIES,
    TESTER_RULES,
    build_tester_context,
    normalize_validation_report,
)


class AutonomousLoopTest(unittest.TestCase):
    def _prepare_git_repo(self, name: str) -> Path:
        root = Path("state") / name
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "config", "user.email", "anubis@example.local"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Anubis Agent"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        (root / ".gitignore").write_text("state/autonomous_git_history.json\n")
        (root / "README.md").write_text("initial\n")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return root.resolve()

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

        with patch.object(loop, "_vector_context_text", return_value="vector context"):
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
        self.assertEqual(memory["agent_communication"]["queue"][0]["recipient"], loop.CODER_AGENT)
        self.assertEqual(memory["agent_communication"]["queue"][0]["type"], "task")

    def test_priority_engine_orders_dependencies_and_parallel_batches(self):
        plan = [
            {"step": 1, "goal": "Inspect repository", "tool_hint": "scan_repo_tree"},
            {"step": 2, "goal": "Implement security fix", "tool_hint": "write_file", "critical": True},
            {"step": 3, "goal": "Run validation tests", "tool_hint": "run_command"},
            {"step": 4, "goal": "Review architecture quality", "phase": "review"},
            {"step": 5, "goal": "Summarize memory", "phase": "memory_summary"},
        ]

        priority_plan = build_priority_plan("Ship secure feature", plan)

        self.assertEqual(priority_plan["dependency_graph"]["step_1"], [])
        self.assertIn("step_1", priority_plan["dependency_graph"]["step_2"])
        self.assertIn("step_2", priority_plan["dependency_graph"]["step_3"])
        self.assertEqual(priority_plan["steps"][0]["id"], "step_2")
        self.assertIn("step_2", priority_plan["critical_path"])
        self.assertTrue(priority_plan["parallel_batches"])

    def test_parallel_batches_group_ready_independent_steps(self):
        steps = [
            {
                "id": "inspect_a",
                "phase": "analysis",
                "priority": 100,
                "depends_on": [],
                "parallelizable": True,
            },
            {
                "id": "inspect_b",
                "phase": "analysis",
                "priority": 90,
                "depends_on": [],
                "parallelizable": True,
            },
            {
                "id": "implement",
                "phase": "action",
                "priority": 120,
                "depends_on": ["inspect_a", "inspect_b"],
                "parallelizable": False,
            },
        ]

        batches = build_parallel_batches(steps)

        self.assertEqual({step["id"] for step in batches[0]}, {"inspect_a", "inspect_b"})
        self.assertEqual(batches[1][0]["id"], "implement")

    def test_developer_project_status_detects_python_workflow(self):
        status = autonomous_developer.developer_project_status(".")

        self.assertIn("python", status["project_types"])
        self.assertEqual(
            status["commands"]["install_dependencies"],
            "python3 -m pip install -r requirements.txt",
        )
        self.assertEqual(status["commands"]["build"], "python3 -m compileall .")
        self.assertEqual(status["commands"]["test"], "python3 -m unittest discover -s tests")

    def test_create_project_scaffold_creates_minimal_python_project(self):
        root = Path("state") / "test_scaffold_project"
        if root.exists():
            shutil.rmtree(root)

        result = autonomous_developer.create_project_scaffold(
            project_type="python",
            path=str(root),
            name="demo",
        )

        self.assertTrue(result["success"])
        self.assertTrue((root / "app.py").exists())
        self.assertTrue((root / "tests" / "test_app.py").exists())
        self.assertIn("run_project_tests", loop.TOOL_SPECS)

        shutil.rmtree(root)

    def test_developer_build_and_test_commands_return_structured_results(self):
        root = Path("state") / "test_dev_project"
        if root.exists():
            shutil.rmtree(root)
        (root / "tests").mkdir(parents=True)
        (root / "app.py").write_text("def main():\n    return 'ok'\n", encoding="utf-8")
        (root / "tests" / "test_app.py").write_text(
            "import unittest\n\n"
            "from app import main\n\n\n"
            "class AppTest(unittest.TestCase):\n"
            "    def test_main(self):\n"
            "        self.assertEqual(main(), 'ok')\n",
            encoding="utf-8",
        )

        build = autonomous_developer.run_project_build(
            command="python3 -m py_compile app.py",
            root=str(root),
        )
        tests = autonomous_developer.run_project_tests(
            command="python3 -m unittest discover -s tests",
            root=str(root),
        )

        self.assertTrue(build["success"], build)
        self.assertEqual(build["stage"], "build")
        self.assertTrue(tests["success"], tests)
        self.assertEqual(tests["stage"], "test")

        shutil.rmtree(root)

    def test_start_and_stop_project_server_tracks_process(self):
        root = Path("state") / "test_server_project"
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        (root / "server.py").write_text(
            "import time\n\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )

        started = autonomous_developer.start_project_server(
            command="python3 server.py",
            root=str(root),
            name="test_dev_server",
            wait_seconds=0.1,
        )
        stopped = autonomous_developer.stop_project_server(name="test_dev_server")

        self.assertTrue(started["success"], started)
        self.assertEqual(started["status"], "running")
        self.assertTrue(stopped["success"], stopped)
        self.assertEqual(stopped["status"], "stopped")

        shutil.rmtree(root)

    def test_developer_mode_tools_are_registered(self):
        expected_tools = {
            "developer_project_status",
            "developer_autonomy_plan",
            "create_project_scaffold",
            "install_project_dependencies",
            "run_project_build",
            "run_project_tests",
            "start_project_server",
            "stop_project_server",
        }

        self.assertTrue(expected_tools.issubset(tool_executor.TOOLS))
        self.assertTrue(expected_tools.issubset(loop.TOOL_SPECS))

    def test_hermes_memory_stores_obsidian_note_and_recalls_context(self):
        memory_file = Path("state") / "test_hermes_memory.json"
        vault = Path("state") / "test_obsidian_vault"
        vector_store = Path("state") / "test_hermes_vector_store.json"
        for path in (memory_file, vector_store):
            if path.exists():
                path.unlink()
        if vault.exists():
            shutil.rmtree(vault)

        with (
            patch.object(hermes_memory, "HERMES_MEMORY_FILE", memory_file),
            patch.object(hermes_memory, "OBSIDIAN_VAULT_PATH", vault),
            patch.object(vector_memory, "VECTOR_STORE_FILE", vector_store),
        ):
            stored = hermes_memory.store_hermes_memory(
                summary="Remember Obsidian vault setup",
                task="Configure Hermes",
                result="Hermes stores memories in Obsidian notes",
                lessons=["Search memory before acting"],
                tags=["hermes", "obsidian", "user-preference"],
            )
            recall = hermes_memory.hermes_recall("Obsidian Hermes memory", top_k=3)

        self.assertTrue(stored["success"], stored)
        self.assertTrue(stored["note"]["path"].endswith(".md"))
        note_text = Path(stored["note"]["path"]).read_text(encoding="utf-8")
        self.assertIn("rag_ready: true", note_text)
        self.assertIn("# Remember Obsidian vault setup", note_text)
        self.assertTrue(stored["daily_note"]["path"].endswith(".md"))
        self.assertTrue((vault / "memories").exists())
        daily_note = next((vault / "memories").glob("*.md"))
        daily_text = daily_note.read_text(encoding="utf-8")
        self.assertIn("# Memory - ", daily_text)
        self.assertIn("## Key facts", daily_text)
        self.assertIn("## User preferences", daily_text)
        self.assertIn("## Projects", daily_text)
        self.assertIn("## Insights", daily_text)
        self.assertIn("Remember Obsidian vault setup", daily_text)
        self.assertIn("Obsidian", recall["context"])
        self.assertTrue(recall["context"].startswith("### Memory Context"))
        self.assertNotIn("score=", recall["context"])
        self.assertNotIn("Hermes JSON memory", recall["context"])
        self.assertTrue(recall["json_matches"])
        self.assertTrue(recall["obsidian_matches"])

        if vault.exists():
            shutil.rmtree(vault)
        for path in (memory_file, vector_store):
            if path.exists():
                path.unlink()

    def test_hermes_tools_are_registered_and_prompts_use_memory(self):
        expected_tools = {
            "search_hermes_memory",
            "index_obsidian_vault",
            "store_hermes_memory",
            "write_obsidian_note",
            "append_daily_memory_summary",
        }
        memory = loop._initial_memory("Remember useful project context", use_planner=True)

        with patch.object(loop, "_hermes_context_text", return_value="Hermes remembered context"):
            analysis_prompt = loop._build_analysis_prompt("Remember useful project context", memory)
            action_prompt = loop._build_action_prompt("Remember useful project context", memory)

        self.assertTrue(expected_tools.issubset(tool_executor.TOOLS))
        self.assertTrue(expected_tools.issubset(loop.TOOL_SPECS))
        self.assertIn("Hermes remembered context", analysis_prompt)
        self.assertIn("Hermes remembered context", action_prompt)
        self.assertIn("search_hermes_memory", analysis_prompt)
        self.assertTrue(callable(hermes_tools.search_hermes_memory))

    def test_capability_detection_gates_obsidian_rag_context(self):
        with patch.object(loop, "OBSIDIAN_RAG_ENABLED", False):
            memory = loop._initial_memory("Answer without local memory", use_planner=True)
            with patch.object(loop, "_hermes_context_text", return_value="should not appear"):
                analysis_prompt = loop._build_analysis_prompt("Answer without local memory", memory)

        self.assertFalse(memory["capabilities"]["OBSIDIAN_RAG"]["enabled"])
        self.assertIn("OBSIDIAN_RAG disabled", analysis_prompt)
        self.assertIn("vector/local knowledge context was not consulted", analysis_prompt)
        self.assertNotIn("should not appear", analysis_prompt)

    def test_query_cache_stores_and_recalls_similar_answers(self):
        cache_file = Path("state") / "test_query_cache.json"
        if cache_file.exists():
            cache_file.unlink()

        with patch.object(query_cache, "QUERY_CACHE_FILE", cache_file):
            stored = query_cache.store_query_cache(
                "Explain OSINT pivot workflow",
                "Use cache, then Obsidian, then external ingestion.",
                context="memory context",
                metadata={"domain": "osint"},
            )
            exact = query_cache.lookup_query_cache("Explain OSINT pivot workflow")
            similar = query_cache.lookup_query_cache("Explain OSINT pivot workflow steps")

        self.assertTrue(stored["stored"])
        self.assertIn("query_embedding", stored["entry"])
        self.assertTrue(exact["hit"])
        self.assertGreaterEqual(exact["confidence"], 0.85)
        self.assertEqual(exact["next_layer"], "final")
        self.assertTrue(similar["hit"])
        self.assertIn("semantic_confidence", similar["best"])
        self.assertIn("Obsidian", similar["best"]["result"])
        cache_file.unlink(missing_ok=True)

    def test_high_confidence_cache_hit_short_circuits_non_code_task(self):
        events = []

        class FakeMemory:
            def __init__(self):
                self.saved = []

            def load(self):
                return {}

            def save(self, memory):
                self.saved.append(dict(memory))

            def append_event(self, memory, event):
                memory.setdefault("actions", []).append(event)

            def context_summary(self, memory):
                return "context"

        class ToolExecutor:
            def execute(self, tool, args=None):
                raise AssertionError(f"cache hit should not execute tool {tool}")

        deps = loop.AgentDependencies(
            tool_executor=ToolExecutor(),
            memory=FakeMemory(),
            call_agent=lambda agent, prompt, context="": "{}",
            query_cache_lookup=lambda query: {
                "enabled": True,
                "hit": True,
                "confidence": 0.95,
                "best": {
                    "query": query,
                    "result": "cached grounded answer",
                    "confidence": 0.95,
                },
                "matches": [
                    {
                        "query": query,
                        "result": "cached grounded answer",
                        "confidence": 0.95,
                    }
                ],
            },
        )

        result = loop.run_agent_loop(
            "Explain OSINT pivot workflow",
            progress_callback=events.append,
            dependencies=deps,
        )

        self.assertEqual(result, "cached grounded answer")
        self.assertIn("query_cache", {event["type"] for event in events})
        self.assertIn("complete", {event["type"] for event in events})

    def test_osint_tool_registration_is_opt_in(self):
        with patch.object(tool_executor, "OSINT_CRAWLER_ENABLED", False), patch.object(tool_executor, "_PLUGINS", None):
            self.assertNotIn("fetch_external_data", tool_executor.build_tool_registry())
            self.assertNotIn("crawl_osint_sources", tool_executor.build_tool_registry())

        with patch.object(tool_executor, "OSINT_CRAWLER_ENABLED", True), patch.object(tool_executor, "_PLUGINS", None):
            registry = tool_executor.build_tool_registry()
            self.assertIn("fetch_external_data", registry)
            self.assertIn("crawl_osint_sources", registry)

    def test_osint_crawler_extracts_actionable_markdown_notes(self):
        from tools import osint

        payloads = {
            "https://example.test/source": {
                "url": "https://example.test/source",
                "status_code": 200,
                "content_type": "text/html",
                "truncated": False,
                "text": """
                    Subscribe now. Advertisement.
                    Tool usage: run nuclei -t cves/ against exposed services.
                    Detection workflow: collect IOC domains, enrich with passive DNS, then write Sigma rules.
                    Marketing paragraph with no technical value.
                """,
            }
        }

        with patch.object(osint, "fetch_external_data", side_effect=lambda url, **kwargs: payloads[url]):
            result = osint.crawl_osint_sources(
                "nuclei osint detection",
                seeds=["https://example.test/source"],
                max_sources=1,
            )

        self.assertEqual(result["notes_ready"], 1)
        note = result["notes"][0]["content"]
        self.assertIn("## Technical Extract", note)
        self.assertIn("nuclei", note)
        self.assertIn("Sigma", note)
        self.assertNotIn("Subscribe now", note)

    def test_hermes_memory_can_mirror_vectors_to_qdrant(self):
        memory_file = Path("state") / "test_hermes_qdrant_memory.json"
        vault = Path("state") / "test_qdrant_obsidian_vault"
        vector_store = Path("state") / "test_qdrant_vector_store.json"
        for path in (memory_file, vector_store):
            if path.exists():
                path.unlink()
        if vault.exists():
            shutil.rmtree(vault)

        with (
            patch.object(hermes_memory, "HERMES_MEMORY_FILE", memory_file),
            patch.object(hermes_memory, "OBSIDIAN_VAULT_PATH", vault),
            patch.object(hermes_memory, "HERMES_MEMORY_BACKEND", "qdrant"),
            patch.object(hermes_memory, "QDRANT_URL", "http://qdrant:6333"),
            patch.object(vector_memory, "VECTOR_STORE_FILE", vector_store),
            patch.object(hermes_memory.requests, "put") as qdrant_put,
        ):
            stored = hermes_memory.store_hermes_memory(
                summary="Mirror durable memory to Qdrant",
                task="Validate Qdrant mirror",
                result="Vector payload is sent to Qdrant when configured.",
                tags=["qdrant", "memory"],
            )

        self.assertTrue(stored["success"], stored)
        self.assertGreaterEqual(qdrant_put.call_count, 2)
        self.assertIn("/collections/hermes_memory", qdrant_put.call_args_list[0].args[0])

        if vault.exists():
            shutil.rmtree(vault)
        for path in (memory_file, vector_store):
            if path.exists():
                path.unlink()

    def test_priority_engine_is_stored_in_orchestration_memory(self):
        memory = loop._initial_memory("Prioritize work", use_planner=True)
        priority_plan = update_priority_engine(
            memory,
            "Prioritize work",
            [
                {"step": 1, "goal": "Inspect", "tool_hint": "scan_repo_tree"},
                {"step": 2, "goal": "Implement", "tool_hint": "write_file"},
            ],
        )

        self.assertEqual(memory["priority_plan"], priority_plan)
        self.assertEqual(memory["orchestration"]["dependency_graph"], priority_plan["dependency_graph"])
        self.assertIn("parallel_batches", memory["orchestration"])

    def test_inter_agent_queue_orders_delivers_and_records_history(self):
        memory = loop._initial_memory("Coordinate agents", use_planner=True)

        low = enqueue_agent_message(
            memory,
            sender=loop.PLANNER_AGENT,
            recipient=loop.CODER_AGENT,
            message_type="context",
            payload={"note": "architecture context"},
            priority=10,
        )
        high = enqueue_agent_message(
            memory,
            sender=loop.ORCHESTRATOR_AGENT,
            recipient=loop.CODER_AGENT,
            message_type="task",
            payload={"task": "implement feature"},
            priority=90,
        )

        self.assertEqual(memory["agent_communication"]["queue"][0]["id"], high["id"])
        self.assertEqual(memory["agent_communication"]["queue"][1]["id"], low["id"])

        delivered = dequeue_agent_messages(memory, recipient=loop.CODER_AGENT, limit=1)
        snapshot = communication_snapshot(memory)

        self.assertEqual(delivered[0]["id"], high["id"])
        self.assertEqual(delivered[0]["status"], "delivered")
        self.assertEqual(snapshot["stats"]["sent"], 2)
        self.assertEqual(snapshot["stats"]["delivered"], 1)
        self.assertEqual(snapshot["stats"]["pending"], 1)
        self.assertIn("orchestrator_agent -> coder_agent [task/delivered]", communication_context(memory))

    def test_call_agent_delivers_assignment_and_shares_result(self):
        memory = loop._initial_memory("Coordinate one call", use_planner=True)
        events = []

        with (
            patch.object(loop, "call_agent", return_value="implemented result"),
            patch.object(loop, "index_agent_history", return_value={"status": "indexed"}),
        ):
            output = loop._call_agent(
                loop.CODER_AGENT,
                "Implement next step",
                memory,
                phase="action",
                progress_callback=events.append,
            )

        self.assertEqual(output, "implemented result")
        history = memory["agent_communication"]["history"]
        self.assertTrue(any(message["type"] == "task" for message in history))
        self.assertTrue(any(message["type"] == "result" for message in history))
        self.assertTrue(any(message["type"] == "context" for message in history))
        self.assertTrue(any(event["type"] == "agent_messages_delivered" for event in events))

    def test_dynamic_tool_can_be_created_loaded_and_reused(self):
        tool_name = "test_dynamic_echo"
        tool_file = dynamic_tools._tool_path(tool_name)
        metadata_file = dynamic_tools._metadata_path(tool_name)
        tool_file.unlink(missing_ok=True)
        metadata_file.unlink(missing_ok=True)
        tool_executor.TOOLS.pop(tool_name, None)
        try:
            result = tool_executor.execute_tool(
                "create_dynamic_tool",
                {
                    "tool_name": tool_name,
                    "description": "Echo a value with a prefix.",
                    "schema": {"value": "text to echo"},
                    "code": (
                        "def run(value: str, prefix: str = 'echo') -> dict:\n"
                        "    return {'message': f'{prefix}: {value}'}\n"
                    ),
                },
            )
            reused = tool_executor.execute_tool(
                tool_name,
                {"value": "hello", "prefix": "dynamic"},
            )
            listed = tool_executor.execute_tool("list_dynamic_tools", {})

            self.assertTrue(result["success"])
            self.assertTrue(reused["success"])
            self.assertEqual(reused["output"], {"message": "dynamic: hello"})
            self.assertIn(tool_name, {tool["tool_name"] for tool in listed["output"]})
        finally:
            tool_executor.TOOLS.pop(tool_name, None)
            tool_file.unlink(missing_ok=True)
            metadata_file.unlink(missing_ok=True)

    def test_dynamic_tool_rejects_unsafe_python(self):
        tool_name = "test_dynamic_unsafe"
        tool_file = dynamic_tools._tool_path(tool_name)
        metadata_file = dynamic_tools._metadata_path(tool_name)
        tool_file.unlink(missing_ok=True)
        metadata_file.unlink(missing_ok=True)
        result = tool_executor.execute_tool(
            "create_dynamic_tool",
            {
                "tool_name": tool_name,
                "description": "Unsafe tool",
                "code": "import subprocess\n\ndef run() -> str:\n    return subprocess.check_output(['pwd']).decode()\n",
            },
        )

        self.assertFalse(result["success"])
        self.assertIn("Import is not allowed", result["output"]["error"])
        self.assertFalse(tool_file.exists())
        self.assertFalse(metadata_file.exists())

    def test_unknown_tool_guides_agent_to_dynamic_creation(self):
        result = tool_executor.execute_tool("missing_capability_tool", {})

        self.assertFalse(result["success"])
        self.assertIn("create_dynamic_tool", result["output"])

    def test_self_improvement_detects_recurring_failures_and_guides_strategy(self):
        memory = loop._initial_memory("Improve itself", use_planner=True)
        repeated_error = {
            "type": "FileNotFoundError",
            "error": "missing README",
        }
        for step in range(1, 4):
            memory["tool_results"].append(
                {
                    "step": step,
                    "tool": "read_file",
                    "success": False,
                    "output": repeated_error,
                }
            )
            memory["errors"].append(
                {
                    "step": step,
                    "tool": "read_file",
                    "error": repeated_error,
                }
            )

        analysis = analyze_performance(memory)
        suggestions = propose_strategy_improvements(memory)
        guidance = optimize_prompt_guidance(memory)
        state = update_self_improvement_memory(memory)

        self.assertEqual(analysis["success_rate"], 0.0)
        self.assertTrue(analysis["recurring_failures"])
        self.assertTrue(any("find_file" in suggestion for suggestion in suggestions))
        self.assertIn("Continuous improvement guidance", guidance)
        self.assertEqual(memory["self_improvement"], state)

    def test_self_improvement_guidance_is_in_agent_prompts(self):
        memory = loop._initial_memory("Use better strategy", use_planner=True)
        memory["tool_results"] = [
            {"tool": "run_command", "success": False, "output": {"type": "TimeoutExpired"}},
            {"tool": "run_command", "success": False, "output": {"type": "TimeoutExpired"}},
            {"tool": "read_file", "success": True, "output": "ok"},
        ]
        memory["errors"] = [
            {"tool": "run_command", "error": {"type": "TimeoutExpired"}},
            {"tool": "run_command", "error": {"type": "TimeoutExpired"}},
        ]
        memory["last_result"] = {"success": False, "output": "timeout"}

        with patch.object(loop, "_vector_context_text", return_value="vector context"):
            prompts = [
                loop._build_analysis_prompt("Use better strategy", memory),
                loop._build_action_prompt("Use better strategy", memory),
                loop._build_evaluate_success_prompt("Use better strategy", memory, memory["last_result"]),
                loop._build_correction_prompt(
                    task="Use better strategy",
                    memory=memory,
                    tool="run_command",
                    args={"cmd": "slow command"},
                    error_text="timeout",
                    retry_number=1,
                    failure_history=[],
                ),
            ]

        for prompt in prompts:
            self.assertIn("Amelioration continue", prompt)
            self.assertIn("Most failed tools", prompt)

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

    def test_debugger_agent_contract_is_autonomous_and_structured(self):
        memory = loop._initial_memory("Fix stack trace", use_planner=True)
        roster = {agent["name"]: agent for agent in memory["agents"]}
        debugger = roster[loop.DEBUGGER_AGENT]

        self.assertEqual(memory["debugger_agent"]["responsibilities"], DEBUGGER_RESPONSIBILITIES)
        self.assertIn("analyze_stack_traces", DEBUGGER_RESPONSIBILITIES)
        self.assertIn("identify_probable_causes", DEBUGGER_RESPONSIBILITIES)
        self.assertIn("propose_corrections", DEBUGGER_RESPONSIBILITIES)
        self.assertIn("rerun_fixes_automatically", DEBUGGER_RESPONSIBILITIES)
        self.assertIn("remain autonomous", DEBUGGER_RULES)
        self.assertIn("never ask for human help", DEBUGGER_RULES)
        self.assertEqual(debugger["prompt"], DEBUGGER_PROMPT)
        self.assertIn("Debugger report schema", build_debugger_context(memory))

        report = normalize_debugger_report(
            {
                "analysis": "Path missing",
                "probable_causes": "wrong path",
                "retry": True,
                "args": {"path": "README.md"},
                "corrections": "use existing file",
                "reason": "README exists",
                "evidence": {"stack_trace": "Traceback", "error": "FileNotFoundError"},
            }
        )
        self.assertTrue(report["retry"])
        self.assertEqual(report["args"], {"path": "README.md"})
        self.assertEqual(report["probable_causes"], ["wrong path"])
        self.assertEqual(DEBUGGER_REPORT_SCHEMA["retry"], "boolean")

    def test_reviewer_agent_contract_is_senior_critical_and_structured(self):
        memory = loop._initial_memory("Review generated code", use_planner=True)
        roster = {agent["name"]: agent for agent in memory["agents"]}
        reviewer = roster[loop.REVIEWER_AGENT]

        self.assertEqual(memory["reviewer_agent"]["responsibilities"], REVIEWER_RESPONSIBILITIES)
        self.assertIn("review_generated_code", REVIEWER_RESPONSIBILITIES)
        self.assertIn("detect_potential_bugs", REVIEWER_RESPONSIBILITIES)
        self.assertIn("verify_architecture_quality", REVIEWER_RESPONSIBILITIES)
        self.assertIn("propose_improvements", REVIEWER_RESPONSIBILITIES)
        self.assertIn("act as a critical senior engineer", REVIEWER_RULES)
        self.assertIn("do not approve incomplete work", REVIEWER_RULES)
        self.assertEqual(reviewer["prompt"], REVIEWER_PROMPT)
        self.assertIn("Review report schema", build_reviewer_context(memory))

        report = normalize_review_report(
            {
                "success": False,
                "status": "changes_requested",
                "summary": "bug risk",
                "findings": "Potential null handling bug",
                "architecture_notes": "Keeps module boundary",
                "improvements": "Add focused validation",
                "reason": "Needs fix",
            }
        )
        self.assertFalse(report["success"])
        self.assertEqual(report["status"], "changes_requested")
        self.assertEqual(report["findings"][0]["severity"], "medium")
        self.assertEqual(report["architecture_notes"], ["Keeps module boundary"])
        self.assertEqual(REVIEW_REPORT_SCHEMA["success"], "boolean")

    def test_vector_memory_indexes_repository_and_retrieves_context(self):
        test_store_path = vector_memory.workspace_root() / "state" / "test_vector_store.json"

        def fake_store_path():
            return test_store_path

        def fake_embed(text: str) -> list[float]:
            text = text.lower()
            return [
                1.0 if "autonomous" in text else 0.0,
                1.0 if "agent" in text else 0.0,
                1.0 if "docker" in text else 0.0,
            ]

        with (
            patch.object(vector_memory, "_store_path", side_effect=fake_store_path),
            patch.object(vector_memory, "embed_text", side_effect=fake_embed),
        ):
            result = vector_memory.index_repository(root=".", force=True)
            matches = vector_memory.semantic_search("autonomous agent", top_k=3)
            context = vector_memory.retrieve_context("autonomous agent", top_k=2)

        self.assertEqual(result["status"], "indexed")
        self.assertGreater(result["total_documents"], 0)
        self.assertTrue(matches)
        self.assertIn("README.md", {match["source"] for match in matches})
        self.assertIn("autonomous", context.lower())
        test_store_path.unlink(missing_ok=True)

    def test_vector_memory_indexes_agent_history(self):
        test_store_path = vector_memory.workspace_root() / "state" / "test_history_vector_store.json"
        memory = loop._initial_memory("Remember collaboration", use_planner=True)
        memory["agent_messages"] = [
            {
                "agent": loop.CODER_AGENT,
                "phase": "action",
                "message": "Implemented semantic repository search",
            }
        ]

        def fake_store_path():
            return test_store_path

        with (
            patch.object(vector_memory, "_store_path", side_effect=fake_store_path),
            patch.object(vector_memory, "embed_text", return_value=[1.0, 0.0, 0.0]),
        ):
            result = vector_memory.index_agent_history(memory)
            matches = vector_memory.semantic_search("semantic repository search", top_k=1, kind="agent_history")

        self.assertEqual(result["agent_history_documents"], 1)
        self.assertEqual(matches[0]["kind"], "agent_history")
        self.assertIn("semantic repository search", matches[0]["text"])
        test_store_path.unlink(missing_ok=True)

    def test_autonomous_git_commit_validates_before_commit(self):
        repo_root = self._prepare_git_repo("test_git_commit")
        try:
            (repo_root / "README.md").write_text("changed\n")

            with patch.object(git_autonomy, "workspace_root", return_value=repo_root):
                result = git_autonomy.autonomous_git_commit(
                    task="update git automation",
                    message="Update git automation",
                    validation_commands=["git rev-parse --is-inside-work-tree"],
                )
                status = git_autonomy.git_status()

            self.assertTrue(result["success"])
            self.assertEqual(result["status"], "committed")
            self.assertIn("README.md", result["files"])
            self.assertFalse(status["dirty"])
        finally:
            shutil.rmtree(repo_root, ignore_errors=True)

    def test_autonomous_git_commit_aborts_when_validation_fails(self):
        repo_root = self._prepare_git_repo("test_git_validation_failure")
        try:
            original_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (repo_root / "README.md").write_text("broken\n")

            with patch.object(git_autonomy, "workspace_root", return_value=repo_root):
                result = git_autonomy.autonomous_git_commit(
                    task="broken change",
                    validation_commands=["git diff --quiet"],
                )
                status = git_autonomy.git_status()

            current_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertFalse(result["success"])
            self.assertEqual(result["status"], "validation_failed")
            self.assertEqual(current_head, original_head)
            self.assertTrue(status["dirty"])
        finally:
            shutil.rmtree(repo_root, ignore_errors=True)

    def test_autonomous_git_rollback_reverts_last_commit(self):
        repo_root = self._prepare_git_repo("test_git_rollback")
        try:
            (repo_root / "README.md").write_text("committed change\n")

            with patch.object(git_autonomy, "workspace_root", return_value=repo_root):
                commit_result = git_autonomy.autonomous_git_commit(
                    task="rollback demo",
                    message="Update rollback demo",
                    validation_commands=["git rev-parse --is-inside-work-tree"],
                )
                rollback_result = git_autonomy.rollback_last_autonomous_commit()

            self.assertTrue(commit_result["success"])
            self.assertTrue(rollback_result["success"])
            self.assertEqual((repo_root / "README.md").read_text(), "initial\n")
        finally:
            shutil.rmtree(repo_root, ignore_errors=True)

    def test_sandbox_rejects_host_paths_and_shell_escape(self):
        blocked_commands = [
            "cat /etc/passwd",
            "echo $(cat README.md)",
            "echo ok; pwd",
            "echo ok && pwd",
            "curl http://example.com",
            "PYTHONPATH=/tmp python3 -m unittest",
        ]

        for command in blocked_commands:
            with self.subTest(command=command):
                with self.assertRaises(SandboxViolation):
                    validate_command(command)

    def test_run_command_returns_timeout_without_hanging(self):
        with patch("tools.sandbox.TOOL_COMMAND_TIMEOUT", 1):
            result = run_command("sleep 2")

        self.assertEqual(result["code"], 124)
        self.assertTrue(result["timeout"])

    def test_tool_audit_writes_workspace_log(self):
        audit_path = Path("state/test_tool_audit.log").resolve()
        audit_path.unlink(missing_ok=True)
        try:
            with patch("tools.sandbox.TOOL_AUDIT_FILE", Path("state/test_tool_audit.log")):
                audit_tool_action(
                    "success",
                    "read_file",
                    args={"path": "README.md"},
                    success=True,
                    result={"ok": True},
                )

            content = audit_path.read_text()
            self.assertIn('"tool": "read_file"', content)
            self.assertIn('"action": "success"', content)
        finally:
            audit_path.unlink(missing_ok=True)

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
            patch.object(loop, "_vector_context_text", return_value="vector context"),
            patch.object(loop, "index_agent_history", return_value={"status": "indexed"}),
            patch.object(loop, "_soft_limit_reached", side_effect=fake_soft_limit),
            patch.object(loop, "CONTINUOUS_RUN", False),
            patch.object(loop, "remember_interaction", return_value={"success": True}),
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
            patch.object(loop, "_vector_context_text", return_value="vector context"),
            patch.object(loop, "index_agent_history", return_value={"status": "indexed"}),
            patch.object(loop, "remember_interaction", return_value={"success": True}),
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
            patch.object(loop, "_vector_context_text", return_value="vector context"),
            patch.object(loop, "index_agent_history", return_value={"status": "indexed"}),
            patch.object(loop, "remember_interaction", return_value={"success": True}),
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
        self.assertEqual(payload["live"]["tool"], "read_file")
        self.assertEqual(payload["live"]["progress"]["state"], loop.STATE_EXECUTE)

    def test_live_execution_event_renders_shell_logs_and_agent(self):
        event = {
            "type": "tool_result",
            "message": "Tool `run_command` succeeded",
            "state": loop.STATE_EXECUTE,
            "agent": loop.TESTER_AGENT,
            "phase": "validation",
            "tool": "run_command",
            "attempt": 1,
            "result": {
                "success": True,
                "output": {
                    "stdout": "tests passed",
                    "stderr": "",
                    "code": 0,
                    "timeout": False,
                },
            },
        }

        payload = agent_event_payload(event, sequence=8)
        text = format_live_execution_event(event)

        self.assertEqual(payload["live"]["active_agent"], loop.TESTER_AGENT)
        self.assertEqual(payload["live"]["shell"]["stdout"], "tests passed")
        self.assertIn("agent: `tester_agent`", text)
        self.assertIn("Tool: `run_command`", text)
        self.assertIn("**Shell Logs**", text)
        self.assertIn("tests passed", text)

    def test_live_execution_event_renders_plan_and_correction(self):
        plan_event = {
            "type": "plan",
            "message": "Plan ready with 1 step(s)",
            "state": loop.STATE_PLAN,
            "plan": [{"step": 1, "goal": "Run tests", "tool_hint": "run_command"}],
        }
        correction_event = {
            "type": "tool_correction",
            "message": "Auto-correction for `read_file`: use README",
            "state": loop.STATE_FIX,
            "tool": "read_file",
            "analysis": "Path was missing",
            "reason": "README exists",
            "retry": True,
            "corrected_args": {"path": "README.md"},
        }

        plan_text = format_live_execution_event(plan_event)
        correction_text = format_live_execution_event(correction_event)
        correction_payload = agent_event_payload(correction_event, sequence=9)

        self.assertIn("**Planning Steps**", plan_text)
        self.assertIn("Run tests", plan_text)
        self.assertIn("**Automatic Correction**", correction_text)
        self.assertIn("README.md", correction_text)
        self.assertEqual(correction_payload["live"]["correction"]["corrected_args"], {"path": "README.md"})


if __name__ == "__main__":
    unittest.main()
