from __future__ import annotations

from typing import Any

from anubis_tools.core.registry import ToolRegistry
from anubis_tools.sandbox.permissions import PermissionRegistry
from anubis_tools.sandbox.schemas import SecureToolExecutionRequest, ToolPermission


class ToolValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ToolSchemaValidator:
    def __init__(self, *, registry: ToolRegistry, permissions: PermissionRegistry) -> None:
        self._registry = registry
        self._permissions = permissions

    def validate(self, request: SecureToolExecutionRequest) -> tuple[SecureToolExecutionRequest, ToolPermission]:
        definitions = {definition.name: definition for definition in self._registry.list()}
        definition = definitions.get(request.tool_name)
        if definition is None:
            raise ToolValidationError("UNKNOWN_TOOL", "Unknown tool requested")
        self._validate_parameters(definition.input_schema, request.parameters)
        permission = self._permissions.assert_allowed(request.tool_name, request.parameters)
        return request, permission

    def _validate_parameters(self, schema: dict[str, Any], parameters: dict[str, Any]) -> None:
        if schema.get("type", "object") != "object":
            raise ToolValidationError("INVALID_SCHEMA", "Tool input schema must be an object schema")
        required = schema.get("required", [])
        for key in required:
            if key not in parameters:
                raise ToolValidationError("MISSING_PARAMETER", f"Missing required parameter: {key}")
        properties = schema.get("properties", {})
        for key, value in parameters.items():
            property_schema = properties.get(key)
            if property_schema is None:
                raise ToolValidationError("UNKNOWN_PARAMETER", f"Unknown parameter: {key}")
            self._validate_type(key, value, property_schema)

    def _validate_type(self, key: str, value: Any, schema: dict[str, Any]) -> None:
        expected = schema.get("type")
        if expected is None:
            return
        valid = {
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, int | float) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
        }.get(expected, True)
        if not valid:
            raise ToolValidationError("INVALID_PARAMETER_TYPE", f"Parameter {key} must be {expected}")

        if isinstance(value, str):
            min_length = schema.get("minLength")
            max_length = schema.get("maxLength")
            if min_length is not None and len(value) < int(min_length):
                raise ToolValidationError("INVALID_PARAMETER", f"Parameter {key} is too short")
            if max_length is not None and len(value) > int(max_length):
                raise ToolValidationError("INVALID_PARAMETER", f"Parameter {key} is too long")
        if isinstance(value, int | float) and not isinstance(value, bool):
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                raise ToolValidationError("INVALID_PARAMETER", f"Parameter {key} is below minimum")
            if maximum is not None and value > maximum:
                raise ToolValidationError("INVALID_PARAMETER", f"Parameter {key} is above maximum")
