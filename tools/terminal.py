import subprocess
from typing import Any, Dict

from tools.sandbox import secure_command_options, validate_command


def _trim_output(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[:limit], True


def run_command(cmd: str) -> Dict[str, Any]:
    validate_command(cmd)
    options = secure_command_options()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=options["cwd"],
            timeout=options["timeout"],
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        max_output_chars = int(options["max_output_chars"])
        stdout, stdout_truncated = _trim_output(str(stdout), max_output_chars)
        stderr, stderr_truncated = _trim_output(str(stderr), max_output_chars)
        return {
            "stdout": stdout,
            "stderr": stderr,
            "code": 124,
            "timeout": True,
            "timeout_seconds": options["timeout"],
            "truncated": stdout_truncated or stderr_truncated,
        }

    max_output_chars = int(options["max_output_chars"])
    stdout, stdout_truncated = _trim_output(result.stdout, max_output_chars)
    stderr, stderr_truncated = _trim_output(result.stderr, max_output_chars)

    return {
        "stdout": stdout,
        "stderr": stderr,
        "code": result.returncode,
        "timeout": False,
        "truncated": stdout_truncated or stderr_truncated,
    }
