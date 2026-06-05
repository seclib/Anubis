from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_records(path: str | Path, list_keys: tuple[str, ...] = ("records", "items", "data", "results")) -> list[dict[str, Any]]:
    target = Path(path)
    if target.suffix.lower() == ".jsonl":
        with target.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    data = json.loads(target.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in list_keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
        return [data]
    raise ValueError(f"Unsupported JSON record input: {target}")


def load_json_object(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
