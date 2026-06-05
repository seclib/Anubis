"""Production-safe plugin manager for ANUBIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.observability import StructuredLogger
from core.plugins.plugin_interface import BasePlugin, PluginRequest, PluginResult, PluginStatus
from core.plugins.registry import PluginRecord, PluginRegistry
from core.security import (
    AuditLogger,
    KillSwitch,
    PermissionEngine,
    SandboxGuard,
    SandboxRequest,
)


@dataclass(slots=True)
class PluginManager:
    """Coordinates plugin lifecycle and sandbox-mediated execution."""

    registry: PluginRegistry = field(default_factory=PluginRegistry)
    permission_engine: PermissionEngine = field(default_factory=PermissionEngine)
    audit_logger: AuditLogger = field(default_factory=AuditLogger)
    kill_switch: KillSwitch = field(default_factory=KillSwitch)
    logger: StructuredLogger = field(default_factory=StructuredLogger)
    sandbox_guard: SandboxGuard = field(init=False)

    def __post_init__(self) -> None:
        self.sandbox_guard = SandboxGuard(
            permission_engine=self.permission_engine,
            audit_logger=self.audit_logger,
            kill_switch=self.kill_switch,
        )

    def register(self, plugin: BasePlugin) -> PluginRecord:
        record = self.registry.register(plugin)
        self.logger.info(
            component="plugins",
            action="plugin.registered",
            message=f"Plugin registered: {record.manifest.plugin_id}",
            trace_id="trace_plugin_lifecycle",
            metadata={"plugin_id": record.manifest.plugin_id},
        )
        return record

    def start(self, plugin_id: str) -> PluginRecord:
        record = self.registry.record(plugin_id)
        updated = self.registry.update(record.manifest.plugin_id, PluginStatus.STARTED)
        self.logger.info(
            component="plugins",
            action="plugin.started",
            message=f"Plugin started: {plugin_id}",
            trace_id="trace_plugin_lifecycle",
            metadata={"plugin_id": plugin_id},
        )
        return updated

    def stop(self, plugin_id: str) -> PluginRecord:
        record = self.registry.record(plugin_id)
        updated = self.registry.update(record.manifest.plugin_id, PluginStatus.STOPPED)
        self.logger.info(
            component="plugins",
            action="plugin.stopped",
            message=f"Plugin stopped: {plugin_id}",
            trace_id="trace_plugin_lifecycle",
            metadata={"plugin_id": plugin_id},
        )
        return updated

    def execute(self, request: PluginRequest) -> dict[str, Any]:
        try:
            record = self.registry.record(request.plugin_id)
            if record.status != PluginStatus.STARTED:
                return self._failure(
                    request,
                    "PluginStatusError",
                    f"plugin is not started: {request.plugin_id}",
                )

            sandbox_decision = self.sandbox_guard.validate(
                SandboxRequest(
                    actor=f"plugin:{request.plugin_id}",
                    action=f"plugin.{request.action}",
                    resource=f"plugin:{request.plugin_id}",
                    operation="plugin_execute",
                    required_permissions=record.manifest.permissions,
                    metadata={"plugin_id": request.plugin_id},
                )
            )
            if not sandbox_decision.allowed:
                return self._failure(
                    request,
                    "SandboxDenied",
                    sandbox_decision.reason,
                )

            plugin = self.registry.get(request.plugin_id)
            output = plugin.execute(request)
            if not isinstance(output, dict):
                raise TypeError("plugin execute() must return a structured dictionary")
            result = PluginResult(
                ok=True,
                plugin_id=request.plugin_id,
                output=output,
                trace=("plugin.status.started", "sandbox.allowed", "plugin.executed"),
            )
            self.logger.info(
                component="plugins",
                action="plugin.executed",
                message=f"Plugin executed: {request.plugin_id}",
                trace_id=request.trace_id,
                metadata={"plugin_id": request.plugin_id, "action": request.action},
            )
            return result.to_dict()
        except Exception as exc:
            try:
                self.registry.update(request.plugin_id, PluginStatus.FAILED, error=str(exc))
            except LookupError:
                pass
            self.logger.error(
                component="plugins",
                action="plugin.failed",
                message=f"Plugin failed: {request.plugin_id}",
                trace_id=request.trace_id,
                error=exc,
                metadata={"plugin_id": request.plugin_id, "action": request.action},
            )
            return self._failure(
                request,
                exc.__class__.__name__,
                str(exc),
            )

    def _failure(self, request: PluginRequest, error_type: str, message: str) -> dict[str, Any]:
        self.logger.error(
            component="plugins",
            action="plugin.denied",
            message=message,
            trace_id=request.trace_id,
            metadata={"plugin_id": request.plugin_id, "action": request.action},
        )
        return PluginResult(
            ok=False,
            plugin_id=request.plugin_id,
            output={},
            error={"type": error_type, "message": message},
            trace=("plugin.execution.denied",),
        ).to_dict()


__all__ = ["PluginManager"]
