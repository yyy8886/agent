"""Tests for durable, incremental Agent run diagnostics."""

import json
import tempfile
import unittest
from pathlib import Path

from my_agent_next.app.agent_run_log import AgentRunLog


class AgentRunLogTests(unittest.TestCase):
    def test_preserves_output_and_terminal_failure_incrementally(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = AgentRunLog(
                agent_id="mabel",
                thread_id="thread-1",
                user_content="inspect files",
                max_iterations=60,
                root=Path(temporary),
            )
            log.append_output("same phrase " * 4)
            log.finish("run_failed", error_type="RuntimeError", error="repeated")

            records = [
                json.loads(line)
                for line in log.path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [record["event"] for record in records],
                ["run_started", "model_output", "run_failed"],
            )
            self.assertIn("same phrase", records[1]["data"]["text"])
            self.assertEqual(records[-1]["data"]["output_characters"], 48)

    def test_redacts_structured_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = AgentRunLog(
                agent_id="mabel",
                thread_id="thread-1",
                user_content="hello",
                max_iterations=60,
                root=Path(temporary),
            )
            log.write("tool_call", {
                "args": {"api_key": "secret", "path": "safe.txt"},
            })
            record = json.loads(
                log.path.read_text(encoding="utf-8").splitlines()[-1]
            )
            self.assertEqual(record["data"]["args"]["api_key"], "[REDACTED]")
            self.assertEqual(record["data"]["args"]["path"], "safe.txt")


if __name__ == "__main__":
    unittest.main()
