from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ToolStackResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    def render(self) -> str:
        lines = [f"$ {self.command}", f"exit={self.returncode}"]
        if self.stdout.strip():
            lines.extend(["", self.stdout.strip()])
        if self.stderr.strip():
            lines.extend(["", self.stderr.strip()])
        return "\n".join(lines).strip()


class OptionalToolStack:
    def start_metasploit(self) -> ToolStackResult:
        return self._run(["--profile", "exploit-tools", "up", "-d", "metasploit"])

    def start_bloodhound(self) -> ToolStackResult:
        return self._run(["--profile", "graph-tools", "up", "-d", "bloodhound-neo4j", "bloodhound"])

    def stop(self) -> ToolStackResult:
        return self._run(
            [
                "--profile",
                "exploit-tools",
                "--profile",
                "graph-tools",
                "stop",
                "metasploit",
                "bloodhound",
                "bloodhound-neo4j",
            ]
        )

    def status(self) -> ToolStackResult:
        return self._run(
            [
                "--profile",
                "exploit-tools",
                "--profile",
                "graph-tools",
                "ps",
                "metasploit",
                "bloodhound-neo4j",
                "bloodhound",
            ]
        )

    def _run(self, args: list[str]) -> ToolStackResult:
        command = self._compose_command() + args
        env = {**os.environ, "COMPOSE_PROJECT_NAME": os.getenv("COMPOSE_PROJECT_NAME", "anubis")}
        proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        return ToolStackResult(" ".join(command), proc.returncode, proc.stdout, proc.stderr)

    def _compose_command(self) -> list[str]:
        docker_compose = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
        if docker_compose.returncode == 0:
            return ["docker", "compose"]
        legacy = subprocess.run(["docker-compose", "version"], capture_output=True, text=True)
        if legacy.returncode == 0:
            return ["docker-compose"]
        raise RuntimeError("docker compose is required")
