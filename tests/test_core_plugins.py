from __future__ import annotations

import inspect
from json import dumps

from core.plugins import (
    BasePlugin,
    PluginLoader,
    PluginManifest,
    PluginManager,
    PluginRequest,
    PluginStatus,
    PluginType,
)
from core.plugins import loader, plugin_interface, plugin_manager
from core.security import PermissionEffect, PermissionRule


class EchoPlugin(BasePlugin):
    def __init__(self) -> None:
        self.manifest = PluginManifest(
            plugin_id="echo",
            name="Echo",
            version="1.0.0",
            plugin_type=PluginType.TOOL,
            entrypoint="echo",
            capabilities=frozenset({"echo.run"}),
            permissions=frozenset({"echo.run"}),
        )

    def execute(self, request: PluginRequest) -> dict[str, object]:
        return {"message": request.payload.get("message", "")}


class BrokenPlugin(EchoPlugin):
    def execute(self, request: PluginRequest) -> dict[str, object]:
        raise RuntimeError("plugin boom")


def test_loader_reads_declarative_manifest_without_code_import(tmp_path) -> None:
    manifest_path = tmp_path / "plugin.json"
    manifest_path.write_text(
        dumps(
            {
                "plugin_id": "echo",
                "name": "Echo",
                "version": "1.0.0",
                "plugin_type": "tool",
                "entrypoint": "echo",
                "capabilities": ["echo.run"],
                "permissions": ["echo.run"],
            }
        ),
        encoding="utf-8",
    )

    manifest = PluginLoader().load_manifest(manifest_path)

    assert manifest.plugin_id == "echo"
    assert manifest.entrypoint == "echo"
    assert manifest.permissions == frozenset({"echo.run"})


def test_manifest_rejects_path_like_entrypoints() -> None:
    try:
        PluginManifest(
            plugin_id="bad",
            name="Bad",
            version="1.0.0",
            plugin_type=PluginType.TOOL,
            entrypoint="../bad.py",
        )
    except ValueError as exc:
        assert "symbolic identifier" in str(exc)
    else:
        raise AssertionError("expected entrypoint rejection")


def test_registry_rejects_duplicate_plugins() -> None:
    manager = PluginManager()
    manager.register(EchoPlugin())

    try:
        manager.register(EchoPlugin())
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("expected duplicate plugin rejection")


def test_plugin_cannot_execute_until_started() -> None:
    manager = PluginManager()
    manager.register(EchoPlugin())

    result = manager.execute(
        PluginRequest(plugin_id="echo", action="run", payload={"message": "hello"})
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "PluginStatusError"


def test_plugin_execution_is_denied_without_permission_rule() -> None:
    manager = PluginManager()
    manager.register(EchoPlugin())
    manager.start("echo")

    result = manager.execute(
        PluginRequest(plugin_id="echo", action="run", payload={"message": "hello"})
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "SandboxDenied"
    assert manager.audit_logger.records()[-1].allowed is False


def test_plugin_execution_runs_through_sandbox_boundary_when_allowed() -> None:
    manager = PluginManager()
    manager.permission_engine.add_rule(
        PermissionRule(
            actor="plugin:echo",
            actions=frozenset({"plugin.run"}),
            resources=frozenset({"plugin:echo"}),
            permissions=frozenset({"sandbox.execute", "echo.run"}),
            effect=PermissionEffect.ALLOW,
        )
    )
    manager.register(EchoPlugin())
    manager.start("echo")

    result = manager.execute(
        PluginRequest(plugin_id="echo", action="run", payload={"message": "hello"})
    )

    assert result["ok"] is True
    assert result["output"] == {"message": "hello"}
    assert result["trace"] == ["plugin.status.started", "sandbox.allowed", "plugin.executed"]
    assert manager.audit_logger.records()[-1].allowed is True


def test_plugin_failures_are_structured_and_logged() -> None:
    manager = PluginManager()
    manager.permission_engine.add_rule(
        PermissionRule(
            actor="plugin:echo",
            actions=frozenset({"plugin.run"}),
            resources=frozenset({"plugin:echo"}),
            permissions=frozenset({"sandbox.execute", "echo.run"}),
        )
    )
    manager.register(BrokenPlugin())
    manager.start("echo")

    result = manager.execute(PluginRequest(plugin_id="echo", action="run"))

    assert result["ok"] is False
    assert result["error"] == {"type": "RuntimeError", "message": "plugin boom"}
    assert manager.registry.record("echo").status == PluginStatus.FAILED
    assert manager.logger.records()[-1].level == "error"


def test_plugin_modules_do_not_perform_runtime_code_injection() -> None:
    sources = "\n".join(
        inspect.getsource(module)
        for module in (loader, plugin_interface, plugin_manager)
    )

    for token in ("exec(", "eval(", "importlib", "__import__", "subprocess", "os.system"):
        assert token not in sources
