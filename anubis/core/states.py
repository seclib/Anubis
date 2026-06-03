from __future__ import annotations

from enum import StrEnum


class AgentExecutionState(StrEnum):
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RETRYING = "retrying"


__all__ = ["AgentExecutionState"]
