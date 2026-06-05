from __future__ import annotations

import asyncio
import importlib.util
import inspect
import tempfile
import traceback
from pathlib import Path


async def _run_one(fn, kwargs):
    result = fn(**kwargs)
    if inspect.isawaitable(result):
        await result


async def main() -> None:
    failures: list[str] = []
    count = 0
    for path in sorted(Path("tests").glob("test_*.py")):
        if path.name == "test_orchestrator.py":
            print(f"SKIP {path.name} (requires pytest)")
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load test module: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name, fn in sorted(vars(module).items()):
            if not (name.startswith("test_") and callable(fn)):
                continue
            count += 1
            try:
                signature = inspect.signature(fn)
                kwargs = {}
                with tempfile.TemporaryDirectory() as tmp:
                    if "tmp_path" in signature.parameters:
                        kwargs["tmp_path"] = Path(tmp)
                    await _run_one(fn, kwargs)
                print(f"PASS {path.name}::{name}")
            except Exception:
                failures.append(f"{path.name}::{name}")
                print(f"FAIL {path.name}::{name}")
                traceback.print_exc()
    if failures:
        print("failures:", failures)
        raise SystemExit(1)
    print("passed", count)


if __name__ == "__main__":
    asyncio.run(main())
