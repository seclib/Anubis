from __future__ import annotations

from typing import Protocol, TypedDict

from anubis.types import JSONObject, ModelName


class ModelRequest(TypedDict, total=False):
    model: str
    prompt: str
    messages: list[JSONObject]
    metadata: JSONObject


class ModelResponse(TypedDict, total=False):
    model: str
    content: str
    metadata: JSONObject


class ModelRouter(Protocol):
    def select_model(self, purpose: str, metadata: JSONObject) -> ModelName:
        ...

    def generate(self, request: ModelRequest) -> ModelResponse:
        ...


__all__ = ["ModelRequest", "ModelResponse", "ModelRouter"]
