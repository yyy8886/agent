"""Tests for the code-first workflow boundary; no submitted source is executed."""

import math
import unittest
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from my_agent_next.app.workflows import WorkflowDependency, validate_workflow_source
from my_agent_next.app.workflows.contract import _bind_workflow_gateway
from my_agent_next.workflow_sdk import (
    WorkflowContractError,
    WorkflowRunInfo,
    WorkflowRuntime,
    normalize_workflow_payload,
)


VALID_SOURCE = '''
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from my_agent_next.workflow_sdk import WorkflowRuntime

class State(TypedDict, total=False):
    message: str
    answer: str

async def ask_agent(state: State, runtime: Runtime[WorkflowRuntime]):
    result = await runtime.context.call_agent("mabel", {"message": state["message"]})
    return {"answer": result["answer"]}

def build_workflow():
    graph = StateGraph(State, context_schema=WorkflowRuntime)
    graph.add_node("ask_agent", ask_agent)
    graph.add_edge(START, "ask_agent")
    graph.add_edge("ask_agent", END)
    return graph.compile()
'''


class WorkflowContractTests(unittest.TestCase):
    def test_accepts_expected_langgraph_contract_without_executing_source(self):
        source = "raise RuntimeError('must not execute')\n" + VALID_SOURCE
        result = validate_workflow_source(source)
        self.assertFalse(result.valid)
        self.assertEqual(result.issues[0].code, "module_side_effect")
        self.assertIn("langgraph.graph", result.imports)

        valid = validate_workflow_source(VALID_SOURCE)
        self.assertTrue(valid.valid, valid.issues)

    def test_reports_syntax_and_entrypoint_errors(self):
        syntax = validate_workflow_source("def build_workflow(:\n    pass")
        self.assertEqual(syntax.issues[0].code, "syntax_error")

        missing = validate_workflow_source("from typing import TypedDict\n")
        self.assertEqual(missing.issues[0].code, "missing_entrypoint")

        arguments = validate_workflow_source("def build_workflow(runtime):\n    return None\n")
        self.assertEqual(arguments.issues[0].code, "invalid_entrypoint_signature")

        invalid_encoding = validate_workflow_source(chr(0xD800))
        self.assertEqual(invalid_encoding.issues[0].code, "invalid_encoding")

    def test_blocks_repository_imports_and_direct_system_access(self):
        source = '''
import os
from my_agent_next.app.chat_repository import ChatRepository

def build_workflow():
    return open("secret.txt").read()
'''
        result = validate_workflow_source(source)
        codes = [issue.code for issue in result.issues]
        self.assertEqual(codes.count("blocked_import"), 2)
        self.assertIn("blocked_call", codes)

    def test_allows_only_the_public_application_workflow_module(self):
        public = validate_workflow_source(
            "from my_agent_next.workflow_sdk import WorkflowRuntime\n"
            "def build_workflow():\n    return None\n"
        )
        self.assertTrue(public.valid, public.issues)

        private_module = validate_workflow_source(
            "from my_agent_next.app.workflows.executor import Worker\n"
            "def build_workflow():\n    return None\n"
        )
        self.assertIn("blocked_import", [issue.code for issue in private_module.issues])

        private_member = validate_workflow_source(
            "from my_agent_next.workflow_sdk import source_validation\n"
            "def build_workflow():\n    return None\n"
        )
        self.assertIn(
            "blocked_import_member",
            [issue.code for issue in private_member.issues],
        )

    def test_reports_common_static_policy_bypasses_and_import_side_effects(self):
        alias = validate_workflow_source(
            "def build_workflow():\n"
            "    file_opener = open\n"
            "    return file_opener('secret.txt')\n"
        )
        self.assertIn("blocked_call_alias", [issue.code for issue in alias.issues])

        builtins_lookup = validate_workflow_source(
            "def build_workflow():\n"
            "    return __builtins__['open']('secret.txt')\n"
        )
        self.assertIn("blocked_call", [issue.code for issue in builtins_lookup.issues])

        decorator = validate_workflow_source(
            "@print('module side effect')\n"
            "def helper():\n    return None\n"
            "def build_workflow():\n    return None\n"
        )
        self.assertIn("module_side_effect", [issue.code for issue in decorator.issues])

        normal_reflection = validate_workflow_source(
            "def build_workflow():\n    return getattr(object(), '__class__')\n"
        )
        self.assertTrue(normal_reflection.valid, normal_reflection.issues)

    def test_normalizes_plain_json_payload_without_sharing_mutable_state(self):
        original = {"message": "hello", "items": [{"value": 1}], "ok": True}
        normalized = normalize_workflow_payload(original, label="input")
        self.assertEqual(normalized, original)
        self.assertIsNot(normalized, original)
        self.assertIsNot(normalized["items"], original["items"])

    def test_rejects_non_json_payload_values(self):
        invalid_values = [
            {"path": Path("file.txt")},
            {"set": {1, 2}},
            {"nan": math.nan},
            {1: "non-string-key"},
            ["top-level-list"],
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(WorkflowContractError):
                    normalize_workflow_payload(value)

    def test_validates_run_call_chain_metadata(self):
        info = WorkflowRunInfo(
            run_id="run-2",
            root_run_id="run-1",
            workflow_id="child",
            workflow_version=3,
            parent_run_id="run-1",
            parent_node_id="call-child",
            call_depth=1,
        )
        self.assertEqual(info.root_run_id, "run-1")
        with self.assertRaises(WorkflowContractError):
            WorkflowRunInfo("run", "run", "workflow", call_depth=-1)
        with self.assertRaises(WorkflowContractError):
            WorkflowRunInfo("run", "other", "workflow")
        with self.assertRaises(WorkflowContractError):
            WorkflowRunInfo("run", "run", "workflow", permission_mode=[])

    def test_validates_frozen_child_workflow_dependencies(self):
        dependency = WorkflowDependency("summarizer", "summary-flow", 3)
        self.assertEqual(dependency.workflow_version, 3)
        with self.assertRaises(WorkflowContractError):
            WorkflowDependency("bad key", "summary-flow", 3)


class _ExampleState(TypedDict, total=False):
    message: str
    answer: str


class _FakeGateway:
    run_info = WorkflowRunInfo("run", "run", "example", workflow_version=1)

    async def call_agent(
        self, agent_id, inputs, *, timeout_seconds=None, step_id=None, route=None,
    ):
        return {"answer": f"{agent_id}: {inputs['message']}"}

    async def call_tool(self, tool_name, arguments, *, timeout_seconds=None):
        return {"result": None}

    async def call_workflow(self, dependency_key, inputs, *, timeout_seconds=None):
        return inputs

    async def emit_event(self, event_type, data):
        return None

    def raise_if_cancelled(self):
        return None


async def _example_node(
    state: _ExampleState,
    runtime: Runtime[WorkflowRuntime],
) -> dict:
    return await runtime.context.call_agent("mabel", {"message": state["message"]})


class WorkflowLangGraphIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_injects_workflow_runtime_through_langgraph_context(self):
        graph = StateGraph(
            _ExampleState,
            context_schema=WorkflowRuntime,
            input_schema=_ExampleState,
            output_schema=_ExampleState,
        )
        graph.add_node("agent", _example_node)
        graph.add_edge(START, "agent")
        graph.add_edge("agent", END)

        compiled = graph.compile()
        context_schema = compiled.get_context_jsonschema()
        self.assertIn("run_info", context_schema["properties"])
        self.assertIn("dependency_keys", context_schema["properties"])

        runtime = WorkflowRuntime(
            WorkflowRunInfo("run", "run", "example", workflow_version=1),
            dependency_keys=("summarizer",),
        )
        with _bind_workflow_gateway(_FakeGateway()):
            result = await compiled.ainvoke(
                {"message": "hello"},
                context=runtime,
            )
        self.assertEqual(result["answer"], "mabel: hello")

        with _bind_workflow_gateway(_FakeGateway()):
            child_result = await runtime.call_workflow(
                "summarizer",
                {"text": result["answer"]},
            )
        self.assertEqual(child_result, {"text": "mabel: hello"})

        with self.assertRaises(WorkflowContractError):
            await runtime.call_workflow("unpublished-flow", {"text": "hello"})


if __name__ == "__main__":
    unittest.main()
