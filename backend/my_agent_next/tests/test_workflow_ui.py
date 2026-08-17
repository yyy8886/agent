"""Static contracts for workflow controls in the single-page workspace."""

import unittest
from pathlib import Path


INDEX_HTML = (
    Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
)


class WorkflowUiTests(unittest.TestCase):
    def test_new_chat_request_does_not_cancel_existing_run(self):
        api_source = (
            INDEX_HTML.parents[1] / "chat_api.py"
        ).read_text(encoding="utf-8")
        self.assertIn("该对话正在生成回答", api_source)
        self.assertNotIn("previous.cancel()", api_source)

    def test_workspace_persists_threads_per_conversation(self):
        source = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn("wsActiveThreadId:" + "${selection.type}" + ":" + "${selection.id}", source)
        self.assertIn("wsMessageLoadVersion", source)
        self.assertIn("if (loadVersion !== wsMessageLoadVersion) return;", source)

    def test_live_workflow_bubble_is_restored_after_thread_switch(self):
        source = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn("const wsLiveWorkflowRuns = new Map()", source)
        self.assertIn("wsLiveWorkflowRuns.set(workflowThreadId", source)
        self.assertIn("wsLiveWorkflowRuns.get(threadId)", source)
        self.assertIn('$("#wsMessages").appendChild(liveRun.element)', source)
        self.assertIn("wsLiveWorkflowRuns.delete(workflowThreadId)", source)

    def test_workflow_timeout_is_user_configurable_per_workflow(self):
        source = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('id="wsWorkflowTimeout"', source)
        self.assertIn("workflowTimeoutSeconds:${workflowId}", source)
        self.assertIn("timeout_seconds:timeoutSeconds", source)
        self.assertNotIn("timeout_seconds:300", source)
        self.assertIn('max="1800"', source)

    def test_agent_tool_iterations_are_user_configurable_per_workflow(self):
        source = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('id="wsWorkflowAgentIterations"', source)
        self.assertIn("max_agent_iterations:maxAgentIterations", source)
        self.assertIn('max="200"', source)
        self.assertIn("WORKFLOW_AGENT_ITERATIONS_DEFAULT = 60", source)

    def test_agent_chat_tool_iterations_are_user_configurable_per_agent(self):
        source = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('id="wsAgentIterations"', source)
        self.assertIn("agentIterations:", source)
        self.assertIn(
            "max_agent_iterations: maxAgentIterations",
            source,
        )
        self.assertIn("AGENT_ITERATIONS_DEFAULT = 60", source)

    def test_agent_tokens_are_aggregated_per_agent_invocation(self):
        source = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn("const activeAgentStreams = new Map()", source)
        self.assertIn('event.event === "agent_token"', source)
        self.assertIn("stream.text += String(data.text", source)
        self.assertIn('event.event === "agent_output" && finalizeAgentStream', source)


if __name__ == "__main__":
    unittest.main()
