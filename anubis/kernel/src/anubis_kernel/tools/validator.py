from __future__ import annotations

from typing import Any


class ToolValidationError(ValueError):
    pass


def validate_parameters(schema: dict[str, Any], parameters: dict[str, Any]) -> None:
    for key in schema.get("required", []):
        if key not in parameters:
            raise ToolValidationError(f"Missing required parameter: {key}")

    properties = schema.get("properties", {})
    for key, value in parameters.items():
        if key not in properties:
            raise ToolValidationError(f"Unknown parameter: {key}")
        expected = properties[key].get("type")
        if expected == "string" and not isinstance(value, str):
            raise ToolValidationError(f"Parameter must be string: {key}")
        if isinstance(value, str):
            min_length = properties[key].get("minLength", 0)
            max_length = properties[key].get("maxLength", 100000)
            if len(value) < min_length or len(value) > max_length:
                raise ToolValidationError(f"Parameter length invalid: {key}")
