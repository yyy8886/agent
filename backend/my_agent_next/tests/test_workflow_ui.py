"""Static contracts for workflow controls in the single-page workspace."""

import unittest
from pathlib import Path


INDEX_HTML = (
    Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
)


class WorkflowUiTests(unittest.TestCase):
    def test_workflow_timeout_is_user_configurable_per_workflow(self):
        source = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('id="wsWorkflowTimeout"', source)
        self.assertIn("workflowTimeoutSeconds:${workflowId}", source)
        self.assertIn("timeout_seconds:timeoutSeconds", source)
        self.assertNotIn("timeout_seconds:300", source)
        self.assertIn('max="1800"', source)


if __name__ == "__main__":
    unittest.main()
