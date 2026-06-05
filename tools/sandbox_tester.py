from __future__ import annotations

from anubis.sandbox import SandboxRequest, default_sandbox
from anubis.types import Task


def main() -> None:
    sandbox = default_sandbox()
    task = Task(kind="sandbox_probe", required_capabilities=frozenset({"missing.capability"}))
    decision = sandbox.authorize(
        SandboxRequest(task=task, agent_name="probe", requested_capabilities=task.required_capabilities)
    )
    print({"allowed": decision.allowed, "explanation": decision.explanation})


if __name__ == "__main__":
    main()
