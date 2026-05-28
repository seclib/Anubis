import subprocess
from typing import Dict, Any


def run_command(cmd: str) -> Dict[str, Any]:
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True
    )

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "code": result.returncode,
    }