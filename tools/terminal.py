import subprocess
from typing import Dict, Any

from tools.sandbox import secure_command_options, validate_command


def run_command(cmd: str) -> Dict[str, Any]:
    validate_command(cmd)
    options = secure_command_options()
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=options["cwd"],
        timeout=options["timeout"],
    )

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "code": result.returncode,
    }
