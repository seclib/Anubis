"""Autonomous developer workflow tools."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import TOOL_COMMAND_TIMEOUT, TOOL_OUTPUT_MAX_CHARS
from tools.sandbox import (
    relative_to_workspace,
    resolve_workspace_path,
    validate_command,
)


SERVER_STATE_DIR = Path("state") / "dev_servers"
_RUNNING_SERVERS: dict[str, subprocess.Popen[str]] = {}


def _trim_output(value: str | bytes | None) -> tuple[str, bool]:
    if value is None:
        return "", False
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    text = str(value)
    if len(text) <= TOOL_OUTPUT_MAX_CHARS:
        return text, False
    return text[:TOOL_OUTPUT_MAX_CHARS], True


def _safe_root(root: str | Path = ".") -> Path:
    safe_root = resolve_workspace_path(root, must_exist=True)
    if not safe_root.is_dir():
        raise NotADirectoryError(f"Not a directory: {relative_to_workspace(safe_root)}")
    return safe_root


def _state_dir() -> Path:
    path = resolve_workspace_path(SERVER_STATE_DIR, must_exist=False)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _server_name(name: str) -> str:
    normalized = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in name)
    normalized = normalized.strip("-_")
    return normalized[:80] or "default"


def _server_metadata_path(name: str) -> Path:
    return _state_dir() / f"{_server_name(name)}.json"


def _server_log_path(name: str) -> Path:
    return _state_dir() / f"{_server_name(name)}.log"


def _is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _run_command(command: str, root: str | Path = ".") -> dict[str, Any]:
    validate_command(command)
    safe_root = _safe_root(root)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(safe_root),
            timeout=TOOL_COMMAND_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout, stdout_truncated = _trim_output(exc.stdout)
        stderr, stderr_truncated = _trim_output(exc.stderr)
        return {
            "command": command,
            "cwd": relative_to_workspace(safe_root),
            "code": 124,
            "stdout": stdout,
            "stderr": stderr,
            "success": False,
            "timeout": True,
            "timeout_seconds": TOOL_COMMAND_TIMEOUT,
            "truncated": stdout_truncated or stderr_truncated,
        }

    stdout, stdout_truncated = _trim_output(result.stdout)
    stderr, stderr_truncated = _trim_output(result.stderr)
    return {
        "command": command,
        "cwd": relative_to_workspace(safe_root),
        "code": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "success": result.returncode == 0,
        "timeout": False,
        "truncated": stdout_truncated or stderr_truncated,
    }


def _read_package_json(root: Path) -> dict[str, Any]:
    package_json = root / "package.json"
    if not package_json.exists():
        return {}
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _python_test_command(root: Path) -> str | None:
    if (root / "tests").is_dir():
        return "python3 -m unittest discover -s tests"
    if any(root.glob("test_*.py")):
        return "python3 -m unittest discover"
    return None


def _node_script_command(package_data: dict[str, Any], script_name: str) -> str | None:
    scripts = package_data.get("scripts")
    if isinstance(scripts, dict) and script_name in scripts:
        return f"npm run {script_name}"
    return None


def developer_project_status(root: str = ".") -> dict[str, Any]:
    """Detect project workflow commands for autonomous development."""
    safe_root = _safe_root(root)
    package_data = _read_package_json(safe_root)
    project_types: list[str] = []

    if (safe_root / "requirements.txt").exists() or (safe_root / "pyproject.toml").exists():
        project_types.append("python")
    if package_data:
        project_types.append("node")
    if (safe_root / "Dockerfile").exists():
        project_types.append("docker")

    dependency_command = None
    build_command = None
    test_command = None
    server_command = None

    if "python" in project_types:
        if (safe_root / "requirements.txt").exists():
            dependency_command = "python3 -m pip install -r requirements.txt"
        elif (safe_root / "pyproject.toml").exists():
            dependency_command = "python3 -m pip install -e ."
        build_command = "python3 -m compileall ."
        test_command = _python_test_command(safe_root)
        if (safe_root / "api" / "openai_server.py").exists():
            server_command = "python3 -m api.openai_server"
        elif (safe_root / "app" / "main.py").exists():
            server_command = "python3 -m app.main"
        elif (safe_root / "main.py").exists():
            server_command = "python3 main.py"

    if "node" in project_types:
        dependency_command = dependency_command or "npm install"
        build_command = _node_script_command(package_data, "build") or build_command
        test_command = _node_script_command(package_data, "test") or test_command
        server_command = (
            _node_script_command(package_data, "dev")
            or _node_script_command(package_data, "start")
            or server_command
        )

    return {
        "root": relative_to_workspace(safe_root),
        "project_types": project_types or ["unknown"],
        "has_existing_project": bool(project_types),
        "commands": {
            "install_dependencies": dependency_command,
            "build": build_command,
            "test": test_command,
            "start_server": server_command,
        },
        "entrypoints": [
            relative_to_workspace(path)
            for path in [
                safe_root / "main.py",
                safe_root / "app" / "main.py",
                safe_root / "api" / "openai_server.py",
                safe_root / "package.json",
            ]
            if path.exists()
        ],
    }


def create_project_scaffold(
    project_type: str = "python",
    path: str = ".",
    name: str = "app",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a minimal runnable project scaffold inside the workspace."""
    safe_path = resolve_workspace_path(path, must_exist=False)
    if safe_path.exists() and not safe_path.is_dir():
        raise FileExistsError(f"Scaffold path is not a directory: {relative_to_workspace(safe_path)}")
    safe_path.mkdir(parents=True, exist_ok=True)

    normalized_type = project_type.strip().lower()
    created: list[str] = []
    skipped: list[str] = []

    if normalized_type not in {"python", "fastapi"}:
        raise ValueError("Supported scaffold project_type values are: python, fastapi")

    files: dict[str, str]
    if normalized_type == "fastapi":
        files = {
            "requirements.txt": "fastapi\nuvicorn\n",
            "app/__init__.py": "",
            "app/main.py": (
                "from fastapi import FastAPI\n\n"
                f"app = FastAPI(title={name!r})\n\n"
                "@app.get('/')\n"
                "def read_root():\n"
                "    return {'status': 'ok'}\n"
            ),
            "tests/test_app.py": (
                "import unittest\n\n\n"
                "class AppSmokeTest(unittest.TestCase):\n"
                "    def test_smoke(self):\n"
                "        self.assertTrue(True)\n"
            ),
        }
    else:
        files = {
            "README.md": f"# {name}\n\nAutonomous Python project scaffold.\n",
            "app.py": (
                "def main():\n"
                "    return 'ok'\n\n\n"
                "if __name__ == '__main__':\n"
                "    print(main())\n"
            ),
            "tests/test_app.py": (
                "import unittest\n\n"
                "from app import main\n\n\n"
                "class AppTest(unittest.TestCase):\n"
                "    def test_main(self):\n"
                "        self.assertEqual(main(), 'ok')\n"
            ),
        }

    for relative_path, content in files.items():
        target = (safe_path / relative_path).resolve(strict=False)
        resolve_workspace_path(target.parent, must_exist=False).mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            skipped.append(relative_to_workspace(target))
            continue
        target.write_text(content, encoding="utf-8")
        created.append(relative_to_workspace(target))

    return {
        "success": True,
        "project_type": normalized_type,
        "root": relative_to_workspace(safe_path),
        "created": created,
        "skipped": skipped,
        "next_commands": developer_project_status(relative_to_workspace(safe_path))["commands"],
    }


def install_project_dependencies(command: str | None = None, root: str = ".") -> dict[str, Any]:
    """Install project dependencies using a sandbox-validated command."""
    status = developer_project_status(root)
    selected_command = command or status["commands"]["install_dependencies"]
    if not selected_command:
        return {
            "success": True,
            "status": "skipped",
            "message": "No dependency installation command detected.",
            "root": status["root"],
        }
    result = _run_command(selected_command, root)
    result["stage"] = "install_dependencies"
    return result


def run_project_build(command: str | None = None, root: str = ".") -> dict[str, Any]:
    """Run the project build or compile validation command."""
    status = developer_project_status(root)
    selected_command = command or status["commands"]["build"]
    if not selected_command:
        return {
            "success": True,
            "status": "skipped",
            "message": "No build command detected.",
            "root": status["root"],
        }
    result = _run_command(selected_command, root)
    result["stage"] = "build"
    return result


def run_project_tests(command: str | None = None, root: str = ".") -> dict[str, Any]:
    """Run project tests and return structured validation output."""
    status = developer_project_status(root)
    selected_command = command or status["commands"]["test"]
    if not selected_command:
        return {
            "success": True,
            "status": "skipped",
            "message": "No test command detected.",
            "root": status["root"],
        }
    result = _run_command(selected_command, root)
    result["stage"] = "test"
    if not result["success"]:
        result["errors"] = [
            line
            for line in (result["stderr"] + "\n" + result["stdout"]).splitlines()
            if "error" in line.lower() or "fail" in line.lower() or "traceback" in line.lower()
        ][:20]
    return result


def start_project_server(
    command: str | None = None,
    root: str = ".",
    name: str = "default",
    wait_seconds: float = 1.0,
) -> dict[str, Any]:
    """Start a project server as a tracked background process."""
    status = developer_project_status(root)
    selected_command = command or status["commands"]["start_server"]
    if not selected_command:
        return {
            "success": False,
            "status": "missing_command",
            "message": "No server start command detected.",
            "root": status["root"],
        }

    validate_command(selected_command)
    safe_root = _safe_root(root)
    normalized_name = _server_name(name)
    metadata_path = _server_metadata_path(normalized_name)
    if metadata_path.exists():
        try:
            previous = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
        previous_pid = previous.get("pid")
        if isinstance(previous_pid, int) and _is_process_running(previous_pid):
            return {
                "success": True,
                "status": "already_running",
                "name": normalized_name,
                "pid": previous_pid,
                "log_file": previous.get("log_file"),
            }

    log_path = _server_log_path(normalized_name)
    log_file = log_path.open("a", encoding="utf-8")
    log_file.write(f"\n[{datetime.now(timezone.utc).isoformat()}] start: {selected_command}\n")
    log_file.flush()
    process = subprocess.Popen(
        selected_command,
        shell=True,
        cwd=str(safe_root),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(max(0.0, min(float(wait_seconds), 5.0)))
    running = process.poll() is None
    if running:
        _RUNNING_SERVERS[normalized_name] = process
    metadata = {
        "name": normalized_name,
        "pid": process.pid,
        "command": selected_command,
        "root": relative_to_workspace(safe_root),
        "log_file": relative_to_workspace(log_path),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "running": running,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    log_file.close()

    return {
        "success": running,
        "status": "running" if running else "exited",
        "name": normalized_name,
        "pid": process.pid,
        "code": process.returncode,
        "log_file": relative_to_workspace(log_path),
    }


def stop_project_server(name: str = "default") -> dict[str, Any]:
    """Stop a server process previously started by start_project_server."""
    normalized_name = _server_name(name)
    metadata_path = _server_metadata_path(normalized_name)
    if not metadata_path.exists():
        return {"success": True, "status": "not_found", "name": normalized_name}

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    pid = metadata.get("pid")
    if not isinstance(pid, int):
        metadata_path.unlink(missing_ok=True)
        return {"success": True, "status": "invalid_metadata_removed", "name": normalized_name}

    if _is_process_running(pid):
        process = _RUNNING_SERVERS.pop(normalized_name, None)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        else:
            return {
                "success": False,
                "status": "untracked_running",
                "name": normalized_name,
                "pid": pid,
                "message": "Server pid is running but is not owned by this tool process.",
            }

    metadata["running"] = False
    metadata["stopped_at"] = datetime.now(timezone.utc).isoformat()
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"success": True, "status": "stopped", "name": normalized_name, "pid": pid}


def developer_autonomy_plan(root: str = ".") -> dict[str, Any]:
    """Return the autonomous developer workflow for the current project."""
    status = developer_project_status(root)
    commands = status["commands"]
    steps = [
        {
            "id": "inspect_project",
            "goal": "Detect project type, files, commands, and missing scaffold.",
            "tool": "developer_project_status",
            "critical": True,
        },
        {
            "id": "create_project",
            "goal": "Create a minimal project scaffold if no project exists.",
            "tool": "create_project_scaffold",
            "critical": not status["has_existing_project"],
        },
        {
            "id": "install_dependencies",
            "goal": "Install dependencies when a dependency command exists.",
            "tool": "install_project_dependencies",
            "command": commands["install_dependencies"],
            "depends_on": ["inspect_project", "create_project"],
        },
        {
            "id": "build",
            "goal": "Run compile/build validation and capture errors.",
            "tool": "run_project_build",
            "command": commands["build"],
            "depends_on": ["install_dependencies"],
            "critical": True,
        },
        {
            "id": "test",
            "goal": "Run project tests and return structured failures.",
            "tool": "run_project_tests",
            "command": commands["test"],
            "depends_on": ["build"],
            "critical": True,
        },
        {
            "id": "start_server",
            "goal": "Launch the app server after successful validation.",
            "tool": "start_project_server",
            "command": commands["start_server"],
            "depends_on": ["test"],
        },
        {
            "id": "debug_retry",
            "goal": "Analyze failed build/test/server output, patch root cause, and retry.",
            "tool": "debugger_agent",
            "depends_on": ["build", "test", "start_server"],
            "critical": True,
        },
    ]
    return {
        "root": status["root"],
        "mode": "autonomous_developer",
        "status": status,
        "steps": steps,
        "success_policy": "continue until build, tests, and server validation succeed or total blockage is documented",
    }


__all__ = [
    "create_project_scaffold",
    "developer_autonomy_plan",
    "developer_project_status",
    "install_project_dependencies",
    "run_project_build",
    "run_project_tests",
    "start_project_server",
    "stop_project_server",
]
