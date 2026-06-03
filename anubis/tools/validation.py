from __future__ import annotations

from typing import Any

from anubis.tools.errors import ToolValidationError
from anubis.types import JSONObject, JSONSchema, JSONValue


def validate_input(schema: JSONSchema, value: JSONObject) -> None:
    _validate_schema(schema, value, path="input")


def _validate_schema(schema: JSONSchema, value: JSONValue, *, path: str) -> None:
    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(expected_type, value):
        raise ToolValidationError(f"{path} must be {expected_type}")

    if expected_type == "object":
        if not isinstance(value, dict):
            raise ToolValidationError(f"{path} must be object")
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise ToolValidationError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        for key, item in value.items():
            child_schema = properties.get(key)
            if child_schema is not None:
                _validate_schema(child_schema, item, path=f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise ToolValidationError(f"{path}.{key} is not allowed")

    if expected_type == "array":
        if not isinstance(value, list):
            raise ToolValidationError(f"{path} must be array")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                _validate_schema(item_schema, item, path=f"{path}[{index}]")


def _matches_type(expected_type: str, value: Any) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


__all__ = ["validate_input"]
