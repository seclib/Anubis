import json
import tempfile
import unittest
from pathlib import Path

from anubis.tools import BaseTool, ToolExecutionContext
from anubis.tools.engine import ToolExecutionEngine
from anubis.tools.filesystem import ReadFileTool, WriteFileTool
from anubis.tools.logging import ToolCallLogger
from anubis.tools.registry import ToolRegistry
from anubis.types import JSONObject, JSONSchema, JSONValue


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo a message."
    input_schema: JSONSchema = {
        "type": "object",
        "required": ["message"],
        "additionalProperties": False,
        "properties": {"message": {"type": "string"}},
    }
    output_schema: JSONSchema = {
        "type": "object",
        "required": ["message"],
        "properties": {"message": {"type": "string"}},
    }

    def run(self, input: JSONObject, context: ToolExecutionContext) -> JSONValue:
        context.log("echo executed")
        return {"message": input["message"]}


class ToolSystemTest(unittest.TestCase):
    def test_registry_discovers_and_engine_executes_dynamic_tool(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            log_path = Path(directory) / "tools.jsonl"
            registry = ToolRegistry()
            engine = ToolExecutionEngine(registry=registry, logger=ToolCallLogger(log_path))

            engine.register(EchoTool())
            result = engine.execute("echo", {"message": "hello"})

            self.assertTrue(result["success"])
            self.assertEqual(result["output"], {"message": "hello"})
            self.assertEqual([tool.name for tool in engine.discover()], ["echo"])
            self.assertTrue(log_path.exists())
            log_event = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(log_event["result"]["tool"], "echo")

    def test_engine_returns_structured_validation_failure(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            engine = ToolExecutionEngine(
                registry=ToolRegistry([EchoTool()]),
                logger=ToolCallLogger(Path(directory) / "tools.jsonl"),
            )

            result = engine.execute("echo", {})

            self.assertFalse(result["success"])
            self.assertEqual(result["tool"], "echo")
            self.assertIn("required", result["error"])
            self.assertTrue(result["output"]["retry_safe"])

    def test_filesystem_tools_read_and_write_through_engine(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            log_path = Path(directory) / "tools.jsonl"
            engine = ToolExecutionEngine(
                registry=ToolRegistry([ReadFileTool(), WriteFileTool()]),
                logger=ToolCallLogger(log_path),
            )
            target = Path(directory) / "note.txt"

            write_result = engine.execute("write_file", {"path": str(target), "content": "ANUBIS"})
            read_result = engine.execute("read_file", {"path": str(target)})

            self.assertTrue(write_result["success"])
            self.assertTrue(read_result["success"])
            self.assertEqual(read_result["output"]["content"], "ANUBIS")
            self.assertEqual(len(log_path.read_text(encoding="utf-8").splitlines()), 2)

    def test_unknown_tool_is_structured_failure(self) -> None:
        with tempfile.TemporaryDirectory(dir="state") as directory:
            engine = ToolExecutionEngine(
                registry=ToolRegistry(),
                logger=ToolCallLogger(Path(directory) / "tools.jsonl"),
            )

            result = engine.execute("missing", {})

            self.assertFalse(result["success"])
            self.assertEqual(result["tool"], "missing")
            self.assertIn("unknown tool", result["error"])


if __name__ == "__main__":
    unittest.main()
