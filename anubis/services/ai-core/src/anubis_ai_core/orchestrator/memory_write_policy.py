from __future__ import annotations

from anubis_ai_core.models.orchestration import MemoryWriteDecision


class MemoryWritePolicy:
    def decide(self, *, user_input: str, final_response: str, approved: bool) -> MemoryWriteDecision:
        lowered = user_input.lower()
        durable_markers = ("remember", "preference", "decision", "we decided", "save this", "store this")
        if approved and any(marker in lowered for marker in durable_markers):
            return MemoryWriteDecision(
                should_store=True,
                reason="User input contains an explicit durable-memory marker.",
                candidate=f"User input: {user_input}\nFinal response: {final_response}",
                namespace="orchestrator",
                requires_user_confirmation=True,
            )
        return MemoryWriteDecision(
            should_store=False,
            reason="No explicit durable-memory marker was detected. Memory is not auto-written.",
            candidate=None,
            namespace="orchestrator",
            requires_user_confirmation=True,
        )
