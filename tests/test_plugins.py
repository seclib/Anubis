from __future__ import annotations

from anubis import (
    AgentRunResult,
    BasePlugin,
    EventType,
    ExecutionLayer,
    ExecutionStatus,
    InMemoryEventBus,
    PluginContext,
    PluginDependency,
    PluginHook,
    PluginManager,
    PluginManifest,
    PluginRegistry,
    PluginStatus,
    PluginType,
    PluginVersion,
    Sandbox,
    Task,
)


class EchoPlugin(BasePlugin):
    def __init__(self) -> None:
        self.manifest = PluginManifest(
            id="echo",
            name="Echo",
            version="1.0.0",
            plugin_type=PluginType.TOOL,
            capabilities=frozenset({"echo.run"}),
            permissions=frozenset({"echo.run"}),
            hooks=frozenset(
                {
                    PluginHook.ON_REGISTER,
                    PluginHook.ON_START,
                    PluginHook.ON_STOP,
                    PluginHook.ON_TASK,
                }
            ),
        )
        self.calls: list[str] = []

    async def on_register(self, context: PluginContext) -> None:
        self.calls.append(f"register:{context.plugin_id}")

    async def on_start(self, context: PluginContext) -> None:
        self.calls.append(f"start:{context.plugin_id}")

    async def on_stop(self, context: PluginContext) -> None:
        self.calls.append(f"stop:{context.plugin_id}")

    async def on_task(self, task: Task, context: PluginContext) -> AgentRunResult:
        self.calls.append(f"task:{context.plugin_id}:{task.kind}")
        return AgentRunResult({"echo": task.payload.get("message")})


class NamedPlugin(BasePlugin):
    def __init__(
        self,
        plugin_id: str,
        version: str,
        *,
        dependencies: tuple[PluginDependency, ...] = (),
        calls: list[str] | None = None,
    ) -> None:
        self.calls = calls if calls is not None else []
        self.manifest = PluginManifest(
            id=plugin_id,
            name=plugin_id.title(),
            version=version,
            plugin_type=PluginType.TOOL,
            capabilities=frozenset({f"{plugin_id}.run"}),
            permissions=frozenset({f"{plugin_id}.run"}),
            dependencies=dependencies,
        )

    async def on_register(self, context: PluginContext) -> None:
        self.calls.append(f"register:{context.plugin_id}")

    async def on_start(self, context: PluginContext) -> None:
        self.calls.append(f"start:{context.plugin_id}")


async def test_plugin_lifecycle_hooks_emit_events() -> None:
    bus = InMemoryEventBus()
    manager = PluginManager(event_bus=bus)
    plugin = EchoPlugin()

    registered = await manager.register(plugin)
    started = await manager.start("echo")
    stopped = await manager.stop("echo")

    assert registered.status == PluginStatus.REGISTERED
    assert started.status == PluginStatus.STARTED
    assert stopped.status == PluginStatus.STOPPED
    assert plugin.calls == ["register:echo", "start:echo", "stop:echo"]
    assert [event.type for event in bus.events] == [
        EventType.PLUGIN_REGISTERED,
        EventType.PLUGIN_STARTED,
        EventType.PLUGIN_STOPPED,
    ]


async def test_plugin_execute_runs_through_sandbox_when_allowed() -> None:
    bus = InMemoryEventBus()
    manager = PluginManager(
        event_bus=bus,
        execution_layer=ExecutionLayer(event_bus=bus, sandbox=Sandbox()),
    )
    plugin = EchoPlugin()
    await manager.register(plugin)
    await manager.start("echo")

    result = await manager.execute(
        "echo",
        Task(
            kind="echo",
            payload={"message": "hello"},
            required_capabilities=frozenset({"echo.run"}),
        ),
    )

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.result is not None
    assert result.result.output["echo"] == "hello"
    assert EventType.SANDBOX_ALLOWED in [event.type for event in bus.events]
    assert EventType.PLUGIN_EXECUTED in [event.type for event in bus.events]


async def test_plugin_execute_is_denied_without_permission() -> None:
    bus = InMemoryEventBus()
    manager = PluginManager(
        event_bus=bus,
        execution_layer=ExecutionLayer(event_bus=bus, sandbox=Sandbox()),
    )
    plugin = EchoPlugin()
    await manager.register(plugin)
    await manager.start("echo")

    result = await manager.execute(
        "echo",
        Task(
            kind="scan",
            required_capabilities=frozenset({"network.scan"}),
        ),
    )

    assert result.status == ExecutionStatus.FAILED
    assert result.attempts == 0
    assert "missing capabilities" in (result.error or "")
    assert EventType.SANDBOX_DENIED in [event.type for event in bus.events]


async def test_plugin_cannot_execute_until_started() -> None:
    manager = PluginManager()
    await manager.register(EchoPlugin())

    result = await manager.execute("echo", Task(kind="echo"))

    assert result.status == ExecutionStatus.FAILED
    assert result.error == "plugin is not started: echo"


def test_plugin_version_parses_and_orders_versions() -> None:
    assert PluginVersion.parse("1.2") == PluginVersion(1, 2, 0)
    assert PluginVersion.parse("1.2.1") > PluginVersion.parse("1.2.0")


async def test_register_many_resolves_dependency_order() -> None:
    calls: list[str] = []
    manager = PluginManager()
    dependent = NamedPlugin(
        "dependent",
        "1.0.0",
        dependencies=(PluginDependency("base", min_version="1.0.0", max_version="2.0.0"),),
        calls=calls,
    )
    base = NamedPlugin("base", "1.2.0", calls=calls)

    records = await manager.register_many((dependent, base))

    assert [record.manifest.id for record in records] == ["base", "dependent"]
    assert calls == ["register:base", "register:dependent"]


async def test_start_resolves_and_starts_dependencies_first() -> None:
    calls: list[str] = []
    manager = PluginManager()
    await manager.register_many(
        (
            NamedPlugin(
                "dependent",
                "1.0.0",
                dependencies=(PluginDependency("base", min_version="1.0.0"),),
                calls=calls,
            ),
            NamedPlugin("base", "1.0.0", calls=calls),
        )
    )

    started = await manager.start("dependent")

    assert started.manifest.id == "dependent"
    assert calls == [
        "register:base",
        "register:dependent",
        "start:base",
        "start:dependent",
    ]
    assert manager.registry.record("base").status == PluginStatus.STARTED


async def test_register_rejects_missing_dependency() -> None:
    manager = PluginManager()
    plugin = NamedPlugin(
        "dependent",
        "1.0.0",
        dependencies=(PluginDependency("missing", min_version="1.0.0"),),
    )

    try:
        await manager.register(plugin)
    except ValueError as exc:
        assert "missing dependency missing" in str(exc)
    else:
        raise AssertionError("expected missing dependency error")


async def test_register_rejects_incompatible_dependency_version() -> None:
    manager = PluginManager()
    await manager.register(NamedPlugin("base", "1.0.0"))

    try:
        await manager.register(
            NamedPlugin(
                "dependent",
                "1.0.0",
                dependencies=(PluginDependency("base", min_version="2.0.0"),),
            )
        )
    except ValueError as exc:
        assert "incompatible dependency base" in str(exc)
    else:
        raise AssertionError("expected incompatible dependency error")


def test_optional_dependency_does_not_block_resolution() -> None:
    registry = PluginRegistry()
    plugin = NamedPlugin(
        "optional-user",
        "1.0.0",
        dependencies=(PluginDependency("missing", optional=True),),
    )

    record = registry.register(plugin)

    assert record.manifest.id == "optional-user"


def test_dependency_cycle_is_detected_in_registration_batch() -> None:
    registry = PluginRegistry()
    first = NamedPlugin(
        "first",
        "1.0.0",
        dependencies=(PluginDependency("second"),),
    )
    second = NamedPlugin(
        "second",
        "1.0.0",
        dependencies=(PluginDependency("first"),),
    )

    try:
        registry.resolve_registration_order((first, second))
    except ValueError as exc:
        assert "dependency cycle" in str(exc)
    else:
        raise AssertionError("expected dependency cycle error")
