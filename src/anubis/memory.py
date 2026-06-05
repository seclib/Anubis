from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from math import sqrt
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from uuid import uuid4

from anubis.types import utcnow


class MemoryScope(StrEnum):
    GLOBAL = "global"
    SWARM = "swarm"
    AGENT = "agent"
    TASK = "task"
    INCIDENT = "incident"


class MemoryKind(StrEnum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class Sensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    SECRET = "secret"


class MemoryContentType(StrEnum):
    OBSERVATION = "observation"
    SUMMARY = "summary"
    EVIDENCE_REFERENCE = "evidence_reference"
    POLICY = "policy"
    PROCEDURE = "procedure"
    SECRET_REFERENCE = "secret_reference"
    CREDENTIAL_REFERENCE = "credential_reference"
    RAW_SECRET = "raw_secret"


class EncryptionState(StrEnum):
    PLAINTEXT = "plaintext"
    ENCRYPTED = "encrypted"
    EXTERNAL_REFERENCE = "external_reference"


class AccessMode(StrEnum):
    READ = "read"
    WRITE = "write"


class ConflictStrategy(StrEnum):
    REJECT = "reject"
    LAST_WRITE_WINS = "last_write_wins"
    MERGE_METADATA = "merge_metadata"
    KEEP_BOTH = "keep_both"


class ConflictStatus(StrEnum):
    NONE = "none"
    REJECTED = "rejected"
    POLICY_REJECTED = "policy_rejected"
    RESOLVED = "resolved"
    FORKED = "forked"


@dataclass(frozen=True, slots=True)
class MemoryAccess:
    actor_id: str
    scopes: frozenset[MemoryScope]
    scope_ids: frozenset[str] = field(default_factory=frozenset)
    max_sensitivity: Sensitivity = Sensitivity.INTERNAL

    def __post_init__(self) -> None:
        object.__setattr__(self, "scopes", frozenset(self.scopes))
        object.__setattr__(self, "scope_ids", frozenset(self.scope_ids))


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    content: str
    scope: MemoryScope
    scope_id: str
    owner_id: str
    kind: MemoryKind = MemoryKind.SHORT_TERM
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    content_type: MemoryContentType = MemoryContentType.OBSERVATION
    encryption: EncryptionState = EncryptionState.PLAINTEXT
    encryption_key_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"mem_{uuid4().hex}")
    version: int = 1
    parent_id: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ConflictResolution:
    status: ConflictStatus
    record: MemoryRecord | None
    conflict_record: MemoryRecord | None
    explanation: str


@dataclass(frozen=True, slots=True)
class StorageDecision:
    allowed: bool
    requires_encryption: bool
    reason: str


@dataclass(frozen=True, slots=True)
class AgentMemoryGrant:
    agent_id: str
    readable_scopes: frozenset[MemoryScope]
    writable_scopes: frozenset[MemoryScope]
    readable_kinds: frozenset[MemoryKind]
    writable_kinds: frozenset[MemoryKind]
    scope_ids: frozenset[str] = field(default_factory=frozenset)
    max_sensitivity: Sensitivity = Sensitivity.INTERNAL

    def __post_init__(self) -> None:
        object.__setattr__(self, "readable_scopes", frozenset(self.readable_scopes))
        object.__setattr__(self, "writable_scopes", frozenset(self.writable_scopes))
        object.__setattr__(self, "readable_kinds", frozenset(self.readable_kinds))
        object.__setattr__(self, "writable_kinds", frozenset(self.writable_kinds))
        object.__setattr__(self, "scope_ids", frozenset(self.scope_ids))


@dataclass(frozen=True, slots=True)
class VectorEntry:
    memory_id: str
    vector: tuple[float, ...]
    sequence: int
    deleted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "vector", tuple(float(value) for value in self.vector))


@dataclass(frozen=True, slots=True)
class VectorSyncBatch:
    entries: tuple[VectorEntry, ...]
    cursor: int


@dataclass(frozen=True, slots=True)
class SearchResult:
    record: MemoryRecord
    score: float


class MemoryIsolationPolicy:
    _sensitivity_rank = {
        Sensitivity.PUBLIC: 0,
        Sensitivity.INTERNAL: 1,
        Sensitivity.RESTRICTED: 2,
        Sensitivity.SECRET: 3,
    }

    def can_access(self, access: MemoryAccess, record: MemoryRecord) -> bool:
        if record.scope not in access.scopes:
            return False
        if record.scope != MemoryScope.GLOBAL and record.scope_id not in access.scope_ids:
            return False
        return (
            self._sensitivity_rank[record.sensitivity]
            <= self._sensitivity_rank[access.max_sensitivity]
        )


@dataclass(frozen=True, slots=True)
class MemoryKindDefinition:
    kind: MemoryKind
    description: str
    default_scope: MemoryScope
    durable: bool
    vector_indexed: bool
    examples: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "examples", tuple(self.examples))


class MemoryKindPolicy:
    def __init__(
        self,
        definitions: Mapping[MemoryKind, MemoryKindDefinition] | None = None,
    ) -> None:
        self._definitions = dict(definitions or default_memory_kind_definitions())

    def definition(self, kind: MemoryKind) -> MemoryKindDefinition:
        return self._definitions[kind]

    def should_vector_index(self, record: MemoryRecord) -> bool:
        return self.definition(record.kind).vector_indexed

    def is_durable(self, record: MemoryRecord) -> bool:
        return self.definition(record.kind).durable

    def explain(self, kind: MemoryKind) -> str:
        definition = self.definition(kind)
        return (
            f"{definition.kind}: {definition.description} "
            f"default_scope={definition.default_scope}; durable={definition.durable}; "
            f"vector_indexed={definition.vector_indexed}."
        )


class SharedMemory:
    """Scoped shared memory with deterministic conflict handling and vector sync."""

    def __init__(
        self,
        *,
        isolation_policy: MemoryIsolationPolicy | None = None,
        kind_policy: MemoryKindPolicy | None = None,
        conflict_strategy: ConflictStrategy = ConflictStrategy.REJECT,
    ) -> None:
        self._records: dict[str, MemoryRecord] = {}
        self._vectors: dict[str, VectorEntry] = {}
        self._vector_log: list[VectorEntry] = []
        self._next_vector_sequence = 1
        self._isolation = isolation_policy or MemoryIsolationPolicy()
        self._kind_policy = kind_policy or MemoryKindPolicy()
        self._conflict_strategy = conflict_strategy

    def put(
        self,
        record: MemoryRecord,
        *,
        expected_version: int | None = None,
        vector: Sequence[float] | None = None,
        strategy: ConflictStrategy | None = None,
    ) -> ConflictResolution:
        current = self._records.get(record.id)
        active_strategy = strategy or self._conflict_strategy
        if current is not None and expected_version is not None and current.version != expected_version:
            return self._resolve_conflict(current, record, active_strategy, vector)

        next_record = record
        if current is not None:
            next_record = replace(record, version=current.version + 1, updated_at=utcnow())
        self._records[next_record.id] = next_record
        if vector is not None and self._kind_policy.should_vector_index(next_record):
            self.upsert_vector(next_record.id, vector)
        return ConflictResolution(
            status=ConflictStatus.NONE,
            record=next_record,
            conflict_record=None,
            explanation="Memory record written without conflict.",
        )

    def get(self, memory_id: str, access: MemoryAccess) -> MemoryRecord | None:
        record = self._records.get(memory_id)
        if record is None or not self._isolation.can_access(access, record):
            return None
        return record

    def query_scope(self, access: MemoryAccess) -> tuple[MemoryRecord, ...]:
        return tuple(
            sorted(
                (
                    record
                    for record in self._records.values()
                    if self._isolation.can_access(access, record)
                ),
                key=lambda record: (record.scope, record.scope_id, record.id),
            )
        )

    def upsert_vector(self, memory_id: str, vector: Sequence[float]) -> VectorEntry:
        if memory_id not in self._records:
            raise KeyError(f"unknown memory record: {memory_id}")
        entry = VectorEntry(
            memory_id=memory_id,
            vector=tuple(vector),
            sequence=self._next_vector_sequence,
        )
        self._vectors[memory_id] = entry
        self._vector_log.append(entry)
        self._next_vector_sequence += 1
        return entry

    def delete_vector(self, memory_id: str) -> VectorEntry:
        entry = VectorEntry(
            memory_id=memory_id,
            vector=(),
            sequence=self._next_vector_sequence,
            deleted=True,
        )
        self._vectors.pop(memory_id, None)
        self._vector_log.append(entry)
        self._next_vector_sequence += 1
        return entry

    def vector_sync(self, *, after_cursor: int = 0, limit: int | None = None) -> VectorSyncBatch:
        entries = [entry for entry in self._vector_log if entry.sequence > after_cursor]
        if limit is not None:
            entries = entries[:limit]
        cursor = entries[-1].sequence if entries else after_cursor
        return VectorSyncBatch(entries=tuple(entries), cursor=cursor)

    def apply_vector_sync(self, batch: VectorSyncBatch) -> int:
        applied = 0
        for entry in sorted(batch.entries, key=lambda item: item.sequence):
            current = self._vectors.get(entry.memory_id)
            if current is not None and current.sequence >= entry.sequence:
                continue
            if entry.deleted:
                self._vectors.pop(entry.memory_id, None)
            else:
                self._vectors[entry.memory_id] = entry
            self._vector_log.append(entry)
            self._next_vector_sequence = max(self._next_vector_sequence, entry.sequence + 1)
            applied += 1
        return applied

    def search(
        self,
        query_vector: Sequence[float],
        access: MemoryAccess,
        *,
        limit: int = 5,
    ) -> tuple[SearchResult, ...]:
        query = tuple(float(value) for value in query_vector)
        results: list[SearchResult] = []
        for memory_id, entry in self._vectors.items():
            record = self._records.get(memory_id)
            if record is None or not self._isolation.can_access(access, record):
                continue
            results.append(SearchResult(record=record, score=_cosine_similarity(query, entry.vector)))
        return tuple(
            sorted(results, key=lambda result: (-result.score, result.record.id))[:limit]
        )

    def _resolve_conflict(
        self,
        current: MemoryRecord,
        incoming: MemoryRecord,
        strategy: ConflictStrategy,
        vector: Sequence[float] | None,
    ) -> ConflictResolution:
        if strategy == ConflictStrategy.REJECT:
            return ConflictResolution(
                status=ConflictStatus.REJECTED,
                record=current,
                conflict_record=incoming,
                explanation=(
                    f"Rejected stale write for {incoming.id}: expected current version "
                    f"{current.version}."
                ),
            )

        if strategy == ConflictStrategy.LAST_WRITE_WINS:
            resolved = replace(incoming, version=current.version + 1, updated_at=utcnow())
            self._records[resolved.id] = resolved
            if vector is not None and self._kind_policy.should_vector_index(resolved):
                self.upsert_vector(resolved.id, vector)
            return ConflictResolution(
                status=ConflictStatus.RESOLVED,
                record=resolved,
                conflict_record=current,
                explanation="Resolved conflict with last-write-wins.",
            )

        if strategy == ConflictStrategy.MERGE_METADATA:
            resolved = replace(
                current,
                content=incoming.content,
                metadata={**dict(current.metadata), **dict(incoming.metadata)},
                version=current.version + 1,
                updated_at=utcnow(),
            )
            self._records[resolved.id] = resolved
            if vector is not None and self._kind_policy.should_vector_index(resolved):
                self.upsert_vector(resolved.id, vector)
            return ConflictResolution(
                status=ConflictStatus.RESOLVED,
                record=resolved,
                conflict_record=current,
                explanation="Resolved conflict by preserving current identity and merging metadata.",
            )

        forked = replace(
            incoming,
            id=f"{incoming.id}_conflict_{uuid4().hex}",
            parent_id=current.id,
            version=1,
            updated_at=utcnow(),
        )
        self._records[forked.id] = forked
        if vector is not None and self._kind_policy.should_vector_index(forked):
            self.upsert_vector(forked.id, vector)
        return ConflictResolution(
            status=ConflictStatus.FORKED,
            record=current,
            conflict_record=forked,
            explanation="Resolved conflict by keeping both records as a fork.",
        )


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def default_memory_kind_definitions() -> Mapping[MemoryKind, MemoryKindDefinition]:
    return {
        MemoryKind.SHORT_TERM: MemoryKindDefinition(
            kind=MemoryKind.SHORT_TERM,
            description="Ephemeral working context for an active task, plan, or swarm session.",
            default_scope=MemoryScope.TASK,
            durable=False,
            vector_indexed=True,
            examples=(
                "current investigation notes",
                "temporary hypotheses",
                "recent tool output summary",
            ),
        ),
        MemoryKind.LONG_TERM: MemoryKindDefinition(
            kind=MemoryKind.LONG_TERM,
            description="Durable operational history retained across sessions.",
            default_scope=MemoryScope.INCIDENT,
            durable=True,
            vector_indexed=True,
            examples=(
                "resolved incident summary",
                "known false positive",
                "asset-specific baseline",
            ),
        ),
        MemoryKind.SEMANTIC: MemoryKindDefinition(
            kind=MemoryKind.SEMANTIC,
            description="Stable factual knowledge used for retrieval and reasoning.",
            default_scope=MemoryScope.GLOBAL,
            durable=True,
            vector_indexed=True,
            examples=(
                "security policy definition",
                "CVE note",
                "approved software fact",
            ),
        ),
        MemoryKind.PROCEDURAL: MemoryKindDefinition(
            kind=MemoryKind.PROCEDURAL,
            description="Reusable instructions, playbooks, and action procedures.",
            default_scope=MemoryScope.GLOBAL,
            durable=True,
            vector_indexed=False,
            examples=(
                "containment playbook",
                "rollback checklist",
                "evidence collection procedure",
            ),
        ),
    }
