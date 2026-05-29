#!/usr/bin/env python3
"""
Anubis Agent V4 - Autonomous Development Agent
CLI entry point for running the agent locally with Ollama
"""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.main import main as run_fastapi_server
from config import (
    API_BASE_PATH,
    API_HOST,
    API_PORT,
    LOG_LEVEL,
    LOG_FORMAT,
    PROJECT_ROOT,
    CONTINUOUS_RUN,
    OLLAMA_MODEL,
)
from agent.loop import run_agent_loop
from agent.streaming import format_progress_event
from memory.state import get_task_state_summary, load_memory

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT
)
logger = logging.getLogger("anubis")

def print_banner():
    """Print welcome banner."""
    print("\n" + "=" * 70)
    print("  ANUBIS AGENT V4 - Autonomous Development Agent")
    print("  Local execution with Ollama")
    print("=" * 70)
    print(f"  Model: {OLLAMA_MODEL}")
    print(f"  Continuous Run: {'✓ ENABLED' if CONTINUOUS_RUN else '✗ Disabled'}")
    print(f"  Project Root: {PROJECT_ROOT}")
    print("=" * 70 + "\n")

def main() -> None:
    """Entry point - run the autonomous agent."""
    print_banner()
    
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "serve":
            api_url = f"http://{API_HOST}:{API_PORT}{API_BASE_PATH or ''}"
            print(f"🌐 Starting FastAPI API on {api_url}\n")
            logger.info("Starting FastAPI API server")
            run_fastapi_server()
            return

        task = input("📝 Enter task (or 'status' to check state): ").strip()
        
        if not task:
            print("❌ Task cannot be empty")
            return
        
        if task.lower() == "status":
            memory = load_memory()
            summary = get_task_state_summary(memory)
            print("\n📊 TASK STATE SUMMARY")
            print("-" * 70)
            print(summary)
            return
        
        print(f"\n🚀 Starting Anubis Agent for:")
        print(f"   {task}\n")
        logger.info(f"Agent starting with task: {task}")
        
        def print_progress(event):
            print(format_progress_event(event), end="", flush=True)

        result = run_agent_loop(task, progress_callback=print_progress)
        memory = load_memory()
        final_status = memory.get("status", "completed")
        
        print("\n" + "=" * 70)
        if final_status == "blocked":
            print("⚠️  TASK BLOCKED")
        else:
            print("✅ TASK COMPLETED")
        print("=" * 70)
        print(f"Status: {final_status}")
        print(f"Result type: {type(result).__name__}")
        if isinstance(result, dict):
            for key, value in result.items():
                print(f"  {key}: {str(value)[:100]}")
        else:
            print(f"  {str(result)[:200]}")
        print("=" * 70 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        logger.warning("Agent interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.exception("Unhandled exception in agent")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
