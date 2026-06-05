"""Recall policy for scoped memory reads."""

from anubis.memory import MemoryAccess, MemoryScope, Sensitivity


def local_recall(actor_id: str, scope_id: str) -> MemoryAccess:
    return MemoryAccess(
        actor_id=actor_id,
        scopes=frozenset({MemoryScope.TASK, MemoryScope.SWARM, MemoryScope.GLOBAL}),
        scope_ids=frozenset({scope_id}),
        max_sensitivity=Sensitivity.INTERNAL,
    )

