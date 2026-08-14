"""Tests for the small direct-execution Workflow builder."""

import unittest

from my_agent_next.app.workflows.contract import _bind_workflow_gateway
from my_agent_next.workflow_sdk import Workflow, WorkflowRunInfo, WorkflowRuntime


class _Gateway:
    async def call_agent(self, agent_id, inputs, *, timeout_seconds=None):
        return {"answer": f"{agent_id}:{inputs['message']}"}

    async def call_tool(self, tool_name, arguments, *, timeout_seconds=None):
        return {"tool": tool_name, "arguments": arguments}

    async def call_skill(self, skill_name, arguments, *, timeout_seconds=None):
        return {"skill": skill_name, "arguments": arguments}

    async def call_workflow(self, dependency_key, inputs, *, timeout_seconds=None):
        return {"answer": inputs["message"]}

    async def emit_event(self, event_type, data):
        return None

    def raise_if_cancelled(self):
        return None


class WorkflowBuilderTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_agent_nodes_and_edges(self):
        flow = Workflow()
        flow.agent(
            "ask",
            agent="mabel",
            message="Improve {message}",
            output="answer",
        )
        flow.edge("START", "ask").edge("ask", "END")

        runtime = WorkflowRuntime(WorkflowRunInfo("run", "run", "builder"))
        with _bind_workflow_gateway(_Gateway()):
            result = await flow.compile().ainvoke(
                {"message": "colors"},
                context=runtime,
            )
        self.assertEqual(result["answer"], "mabel:Improve colors")
        self.assertEqual(result["message"], "colors")

    async def test_builds_native_condition(self):
        flow = Workflow()
        flow.node("check", lambda state: {"approved": state["message"] == "yes"})
        flow.node("accept", lambda state: {"answer": "accepted"})
        flow.node("reject", lambda state: {"answer": "rejected"})
        flow.edge("START", "check")
        flow.if_(
            "check",
            lambda state: state["approved"],
            then="accept",
            otherwise="reject",
        )
        flow.edge("accept", "END").edge("reject", "END")

        runtime = WorkflowRuntime(WorkflowRunInfo("run", "run", "builder"))
        with _bind_workflow_gateway(_Gateway()):
            result = await flow.compile().ainvoke({"message": "no"}, context=runtime)
        self.assertEqual(result["answer"], "rejected")

    async def test_while_has_a_mandatory_hard_limit(self):
        flow = Workflow()
        flow.node("check", lambda state: {**state})
        flow.node(
            "increment",
            lambda state: {**state, "count": state.get("count", 0) + 1},
        )
        flow.node("finish", lambda state: {**state, "answer": str(state["count"])})
        flow.edge("START", "check")
        flow.while_(
            "check",
            lambda state: True,
            body="increment",
            done="finish",
            max_iterations=3,
        )
        flow.edge("finish", "END")

        runtime = WorkflowRuntime(WorkflowRunInfo("run", "run", "builder"))
        with _bind_workflow_gateway(_Gateway()):
            result = await flow.compile().ainvoke(
                {"message": "loop", "count": 0},
                context=runtime,
                config={"recursion_limit": 30},
            )
        self.assertEqual(result["answer"], "3")

        with self.assertRaises(Exception):
            Workflow().while_(
                "check", lambda state: True, body="body", done="END",
                max_iterations=0,
            )


if __name__ == "__main__":
    unittest.main()
