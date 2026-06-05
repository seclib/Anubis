from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from anubis.events import EventBus
from anubis.execution import ExecutionLayer, ExecutionResult, ExecutionStatus
from anubis.sandbox import CapabilityGrant, PermissionSet
from anubis.types import AgentRunResult, Event, EventType, Task


class PluginType(StrEnum):
    SENSOR = "sensor"
    DETECTOR = "detector"
    TOOL = "tool"
    RESPONDER = "responder"
    MODEL = "model"
    KNOWLEDGE = "knowledge"
    UI = "ui"


class PluginStatus(StrEnum):
    REGISTERED = "registered"
    STARTED = "started"
    STOPPED = "stopped"
    FAILED = "failed"


class PluginHook(StrEnum):
    ON_REGISTER = "on_register"
    ON_START = "on_start"
    ON_STOP = "on_stop"
    ON_TASK = "on_task"
    ON_ERROR = "on_error"


@dataclass(frozen=True, slots=True, order=True)
class PluginVersion:
    major: int
    minor: int = 0
    patch: int = 0

    @classmethod
    def parse(cls, value: str) -> "PluginVersion":
        parts = value.split(".")
        if not 1 <= len(parts) <= 3:
            raise ValueError(f"invalid plugin version: {value}")
        parsed = [int(part) for part in parts]
        while len(parsed) < 3:
            parsed.append(0)
        return cls(*parsed)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class PluginDependency:
    plugin_id: str
    min_version: str | None = None
    max_version: str | None = None
    optional: bool = False

    def is_satisfied_by(self, manifest: "PluginManifest") -> bool:
        version = PluginVersion.parse(manifest.version)
        if self.min_version is not None and version < PluginVersion.parse(self.min_version):
            return False
        if self.max_version is not None and version >= PluginVersion.parse(self.max_version):
            return False
        return True

    def describe(self) -> str:
        constraints: list[str] = []
        if self.min_version is not None:
            constraints.append(f">={self.min_version}")
        if self.max_version is not None:
            constraints.append(f"<{self.max_version}")
        suffix = f" ({', '.join(constraints)})" if constraints else ""
        return f"{self.plugin_id}{suffix}"


@dataclass(frozen=True, slots=True)
class DependencyIssue:
    plugin_id: str
    dependency: PluginDependency
    reason: str


@dataclass(frozen=True, slots=True)
class DependencyResolution:
    ok: bool
    order: tuple[str, ...]
    issues: tuple[DependencyIssue, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "order", tuple(self.order))
        object.__setattr__(self, "issues", tuple(self.issues))


@dataclass(frozen=True, slots=True)
class PluginManifest:
    id: str
    name: str
    version: str
    plugin_type: PluginType
    capabilities: frozenset[str]
    hooks: frozenset[PluginHook] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    dependencies: tuple[PluginDependency, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("plugin id is required")
        if not self.name:
            raise ValueError("plugin name is required")
        PluginVersion.parse(self.version)
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        object.__setattr__(self, "hooks", frozenset(self.hooks))
        object.__setattr__(self, "permissions", frozenset(self.permissions))
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class PluginContext:
    plugin_id: str
    status: PluginStatus
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class PluginRecord:
    manifest: PluginManifest
    status: PluginStatus = PluginStatus.REGISTERED
    last_error: str | None = None


class Plugin(Protocol):
    manifest: PluginManifest

    async def on_register(self, context: PluginContext) -> None: ...

    async def on_start(self, context: PluginContext) -> None: ...

    async def on_stop(self, context: PluginContext) -> None: ...

    async def on_task(self, task: Task, context: PluginContext) -> AgentRunResult: ...

    async def on_error(self, error: BaseException, context: PluginContext) -> None: ...


class BasePlugin:
    manifest: PluginManifest

    async def on_register(self, context: PluginContext) -> None:
        return None

    async def on_start(self, context: PluginContext) -> None:
        return None

    async def on_stop(self, context: PluginContext) -> None:
        return None

    async def on_task(self, task: Task, context: PluginContext) -> AgentRunResult:
        raise NotImplementedError("plugin does not implement on_task")

    async def on_error(self, error: BaseException, context: PluginContext) -> None:
        return None


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._records: dict[str, PluginRecord] = {}

    def register(self, plugin: Plugin) -> PluginRecord:
        manifest = plugin.manifest
        if manifest.id in self._plugins:
            raise ValueError(f"plugin already registered: {manifest.id}")
        resolution = self.resolve_manifest_dependencies(manifest)
        if not resolution.ok:
            issue_text = "; ".join(issue.reason for issue in resolution.issues)
            raise ValueError(f"plugin dependencies not satisfied: {issue_text}")
        self._plugins[manifest.id] = plugin
        record = PluginRecord(manifest=manifest)
        self._records[manifest.id] = record
        return record

    def register_many(self, plugins: Sequence[Plugin]) -> tuple[PluginRecord, ...]:
        ordered = self.resolve_registration_order(plugins)
        records: list[PluginRecord] = []
        for plugin in ordered:
            records.append(self.register(plugin))
        return tuple(records)

    def get(self, plugin_id: str) -> Plugin:
        return self._plugins[plugin_id]

    def record(self, plugin_id: str) -> PluginRecord:
        return self._records[plugin_id]

    def update(self, plugin_id: str, status: PluginStatus, error: str | None = None) -> PluginRecord:
        record = replace(self._records[plugin_id], status=status, last_error=error)
        self._records[plugin_id] = record
        return record

    def records(self) -> tuple[PluginRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda record: record.manifest.id))

    def resolve_manifest_dependencies(self, manifest: PluginManifest) -> DependencyResolution:
        issues: list[DependencyIssue] = []
        order: list[str] = []
        for dependency in sorted(manifest.dependencies, key=lambda item: item.plugin_id):
            record = self._records.get(dependency.plugin_id)
            if record is None:
                if dependency.optional:
                    continue
                issues.append(
                    DependencyIssue(
                        plugin_id=manifest.id,
                        dependency=dependency,
                        reason=f"missing dependency {dependency.describe()} for {manifest.id}",
                    )
                )
                continue
            if not dependency.is_satisfied_by(record.manifest):
                issues.append(
                    DependencyIssue(
                        plugin_id=manifest.id,
                        dependency=dependency,
                        reason=(
                            f"incompatible dependency {dependency.describe()} for {manifest.id}; "
                            f"installed {record.manifest.version}"
                        ),
                    )
                )
                continue
            order.append(record.manifest.id)
        return DependencyResolution(ok=not issues, order=tuple(order), issues=tuple(issues))

    def resolve_start_order(self, plugin_id: str) -> DependencyResolution:
        issues: list[DependencyIssue] = []
        order: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(current_id: str) -> None:
            if current_id in visited:
                return
            if current_id in visiting:
                issues.append(
                    DependencyIssue(
                        plugin_id=current_id,
                        dependency=PluginDependency(current_id),
                        reason=f"dependency cycle detected at {current_id}",
                    )
                )
                return
            record = self._records.get(current_id)
            if record is None:
                issues.append(
                    DependencyIssue(
                        plugin_id=current_id,
                        dependency=PluginDependency(current_id),
                        reason=f"plugin is not registered: {current_id}",
                    )
                )
                return
            visiting.add(current_id)
            for dependency in sorted(record.manifest.dependencies, key=lambda item: item.plugin_id):
                dependency_record = self._records.get(dependency.plugin_id)
                if dependency_record is None:
                    if not dependency.optional:
                        issues.append(
                            DependencyIssue(
                                plugin_id=current_id,
                                dependency=dependency,
                                reason=f"missing dependency {dependency.describe()} for {current_id}",
                            )
                        )
                    continue
                if not dependency.is_satisfied_by(dependency_record.manifest):
                    issues.append(
                        DependencyIssue(
                            plugin_id=current_id,
                            dependency=dependency,
                            reason=(
                                f"incompatible dependency {dependency.describe()} for {current_id}; "
                                f"installed {dependency_record.manifest.version}"
                            ),
                        )
                    )
                    continue
                visit(dependency.plugin_id)
            visiting.remove(current_id)
            visited.add(current_id)
            order.append(current_id)

        visit(plugin_id)
        return DependencyResolution(ok=not issues, order=tuple(order), issues=tuple(issues))

    def resolve_registration_order(self, plugins: Sequence[Plugin]) -> tuple[Plugin, ...]:
        by_id = {plugin.manifest.id: plugin for plugin in plugins}
        if len(by_id) != len(tuple(plugins)):
            raise ValueError("duplicate plugin ids in registration batch")
        issues: list[str] = []
        order: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def manifest_for(plugin_id: str) -> PluginManifest | None:
            if plugin_id in self._records:
                return self._records[plugin_id].manifest
            plugin = by_id.get(plugin_id)
            return plugin.manifest if plugin is not None else None

        def visit(plugin_id: str) -> None:
            if plugin_id in visited or plugin_id in self._records:
                return
            if plugin_id in visiting:
                issues.append(f"dependency cycle detected at {plugin_id}")
                return
            plugin = by_id.get(plugin_id)
            if plugin is None:
                return
            visiting.add(plugin_id)
            for dependency in sorted(plugin.manifest.dependencies, key=lambda item: item.plugin_id):
                dependency_manifest = manifest_for(dependency.plugin_id)
                if dependency_manifest is None:
                    if not dependency.optional:
                        issues.append(
                            f"missing dependency {dependency.describe()} for {plugin.manifest.id}"
                        )
                    continue
                if not dependency.is_satisfied_by(dependency_manifest):
                    issues.append(
                        f"incompatible dependency {dependency.describe()} for "
                        f"{plugin.manifest.id}; found {dependency_manifest.version}"
                    )
                    continue
                visit(dependency.plugin_id)
            visiting.remove(plugin_id)
            visited.add(plugin_id)
            order.append(plugin_id)

        for plugin_id in sorted(by_id):
            visit(plugin_id)
        if issues:
            raise ValueError("plugin dependencies not satisfied: " + "; ".join(sorted(set(issues))))
        return tuple(by_id[plugin_id] for plugin_id in order if plugin_id in by_id)


class PluginManager:
    def __init__(
        self,
        *,
        registry: PluginRegistry | None = None,
        execution_layer: ExecutionLayer | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.registry = registry or PluginRegistry()
        self.execution_layer = execution_layer or ExecutionLayer(event_bus=event_bus)
        self.event_bus = event_bus

    async def register(self, plugin: Plugin) -> PluginRecord:
        record = self.registry.register(plugin)
        self._grant_plugin_permissions(record.manifest)
        await plugin.on_register(self._context(record))
        await self._publish(EventType.PLUGIN_REGISTERED, record)
        return record

    async def register_many(self, plugins: Sequence[Plugin]) -> tuple[PluginRecord, ...]:
        ordered = self.registry.resolve_registration_order(plugins)
        records: list[PluginRecord] = []
        for plugin in ordered:
            records.append(await self.register(plugin))
        return tuple(records)

    async def start(self, plugin_id: str) -> PluginRecord:
        resolution = self.registry.resolve_start_order(plugin_id)
        if not resolution.ok:
            issue_text = "; ".join(issue.reason for issue in resolution.issues)
            raise ValueError(f"plugin dependencies not satisfied: {issue_text}")
        record: PluginRecord | None = None
        for resolved_id in resolution.order:
            current = self.registry.record(resolved_id)
            if current.status == PluginStatus.STARTED:
                record = current
                continue
            record = await self._start_one(resolved_id)
        if record is None:
            raise ValueError(f"plugin is not registered: {plugin_id}")
        return record

    async def _start_one(self, plugin_id: str) -> PluginRecord:
        plugin = self.registry.get(plugin_id)
        try:
            await plugin.on_start(self._context(self.registry.record(plugin_id)))
            record = self.registry.update(plugin_id, PluginStatus.STARTED)
            await self._publish(EventType.PLUGIN_STARTED, record)
            return record
        except Exception as exc:
            return await self._fail(plugin_id, exc)

    async def stop(self, plugin_id: str) -> PluginRecord:
        plugin = self.registry.get(plugin_id)
        try:
            await plugin.on_stop(self._context(self.registry.record(plugin_id)))
            record = self.registry.update(plugin_id, PluginStatus.STOPPED)
            await self._publish(EventType.PLUGIN_STOPPED, record)
            return record
        except Exception as exc:
            return await self._fail(plugin_id, exc)

    async def execute(self, plugin_id: str, task: Task) -> ExecutionResult:
        plugin = self.registry.get(plugin_id)
        record = self.registry.record(plugin_id)
        if record.status != PluginStatus.STARTED:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                attempts=0,
                error=f"plugin is not started: {plugin_id}",
                metadata={"plugin_id": plugin_id},
            )

        task = self._plugin_task(plugin.manifest, task)
        result = await self.execution_layer.run(
            task=task,
            agent_name=self._sandbox_agent(plugin_id),
            executor=lambda run_task: plugin.on_task(run_task, self._context(record)),
        )
        if result.status == ExecutionStatus.FAILED and result.error is not None:
            await plugin.on_error(RuntimeError(result.error), self._context(record))
        await self._publish(EventType.PLUGIN_EXECUTED, record, {"task_id": task.id, "status": result.status})
        return result

    def permission_set_for(self, manifest: PluginManifest) -> PermissionSet:
        grants = frozenset(CapabilityGrant(permission) for permission in manifest.permissions)
        return PermissionSet(agent_name=self._sandbox_agent(manifest.id), grants=grants)

    def _grant_plugin_permissions(self, manifest: PluginManifest) -> None:
        sandbox = self.execution_layer.sandbox
        if sandbox is None:
            return
        sandbox.permissions.grant(self.permission_set_for(manifest))

    def _plugin_task(self, manifest: PluginManifest, task: Task) -> Task:
        required = task.required_capabilities or manifest.capabilities
        return Task(
            kind=task.kind,
            payload=task.payload,
            required_capabilities=required,
            priority=task.priority,
            id=task.id,
            correlation_id=task.correlation_id,
            created_at=task.created_at,
            metadata={**dict(task.metadata), "plugin_id": manifest.id},
        )

    def _context(self, record: PluginRecord) -> PluginContext:
        return PluginContext(
            plugin_id=record.manifest.id,
            status=record.status,
            metadata=record.manifest.metadata,
        )

    async def _fail(self, plugin_id: str, exc: BaseException) -> PluginRecord:
        record = self.registry.update(plugin_id, PluginStatus.FAILED, str(exc))
        plugin = self.registry.get(plugin_id)
        await plugin.on_error(exc, self._context(record))
        await self._publish(EventType.PLUGIN_FAILED, record)
        return record

    async def _publish(
        self,
        event_type: EventType,
        record: PluginRecord,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        if self.event_bus is None:
            return
        payload = {
            "plugin_id": record.manifest.id,
            "name": record.manifest.name,
            "version": record.manifest.version,
            "status": record.status,
            "last_error": record.last_error,
            **dict(extra or {}),
        }
        await self.event_bus.publish(Event(type=event_type, producer="plugins", payload=payload))

    def _sandbox_agent(self, plugin_id: str) -> str:
        return f"plugin:{plugin_id}"
