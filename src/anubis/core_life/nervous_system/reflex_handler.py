"""Automatic reflex reactions for urgent events."""

from anubis.safety import KillSwitchDecision


class ReflexHandler:
    def should_interrupt(self, decision: KillSwitchDecision) -> bool:
        return decision.triggered

