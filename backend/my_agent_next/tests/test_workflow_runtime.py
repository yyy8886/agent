"""Integration tests for direct LangGraph artifacts and worker cancellation."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk, SystemMessage

from my_agent_next.app.workflows.artifact import WorkflowArtifactStore
from my_agent_next.app.workflows.model import WorkflowDraft
from my_agent_next.app.workflows.repository import WorkflowRepository
from my_agent_next.app.workflows.run_manager import WorkflowRunManager
from my_agent_next.app.workflows.worker import (
    EventEmitter,
    WorkerGateway,
    WorkerSpec,
    _redact_value,
    _workflow_agent_context,
)


CONDITIONAL_LOOP_SOURCE = '''from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict, total=False):
    message: str
    count: int
    answer: str


def increment(state: State) -> dict:
    count = state.get("count", 0) + 1
    return {"count": count, "answer": f"{state['message']}:{count}"}


def choose(state: State) -> str:
    return "again" if state["count"] < 3 else "done"


def build_workflow():
    graph = StateGraph(State)
    graph.add_node("increment", increment)
    graph.add_edge(START, "increment")
    graph.add_conditional_edges("increment", choose, {"again": "increment", "done": END})
    return graph.compile()
'''


INFINITE_LOOP_SOURCE = '''from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict, total=False):
    message: str
    answer: str


def spin(state: State) -> dict:
    while True:
        pass


def build_workflow():
    graph = StateGraph(State)
    graph.add_node("spin", spin)
    graph.add_edge(START, "spin")
    graph.add_edge("spin", END)
    return graph.compile()
'''


class WorkflowRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.repository = WorkflowRepository(root / "runtime.db")
        self.manager = WorkflowRunManager(
            self.repository,
            WorkflowArtifactStore(root / "artifacts"),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    async def test_runs_native_conditional_edges_and_cycles(self):
        self.repository.save(
            WorkflowDraft("conditional-flow", "Conditional", "", CONDITIONAL_LOOP_SOURCE),
            create=True,
        )
        active = self.manager.start(
            "conditional-flow", {"message": "hello"}, recursion_limit=10,
        )
        events = [event async for event in self.manager.stream(active.run_id)]
        outputs = [event for event in events if event["event"] == "run_output"]
        self.assertEqual(outputs[-1]["data"], {"answer": "hello:3"})
        node_outputs = [event for event in events if event["event"] == "node_output"]
        self.assertEqual(len(node_outputs), 3)

    async def test_hard_stops_non_cooperative_python_while_loop(self):
        self.repository.save(
            WorkflowDraft("infinite-flow", "Infinite", "", INFINITE_LOOP_SOURCE),
            create=True,
        )
        active = self.manager.start(
            "infinite-flow", {"message": "stop"}, timeout_seconds=10,
        )

        async def cancel_soon():
            await asyncio.sleep(0.2)
            self.assertTrue(self.manager.cancel(active.run_id))

        cancel_task = asyncio.create_task(cancel_soon())
        events = [event async for event in self.manager.stream(active.run_id)]
        await cancel_task
        self.assertTrue(any(event["event"] == "run_cancelled" for event in events))
        self.assertFalse(active.process.is_alive())

    def test_redacts_sensitive_event_fields_recursively(self):
        value = _redact_value({"input": {"api_key": "secret", "city": "北京"}, "token_count": 12})
        self.assertEqual(value["input"]["api_key"], "[REDACTED]")
        self.assertEqual(value["input"]["city"], "北京")
        self.assertEqual(value["token_count"], 12)

    def test_workflow_agent_context_identifies_route_and_current_step(self):
        context = _workflow_agent_context(
            workflow_id="review-flow",
            step_id="norden_reviews",
            route="- START -> mabel_works\n- mabel_works -> norden_reviews\n- norden_reviews -> END",
            call_depth=0,
            permission_mode="manual",
            dependency_keys=("child",),
        )
        self.assertIn("工作流 ID：review-flow", context)
        self.assertIn("你当前所在步骤：norden_reviews", context)
        self.assertIn("mabel_works -> norden_reviews", context)
        self.assertIn("已声明子工作流依赖：child", context)

    async def test_worker_injects_step_context_into_actual_agent_messages(self):
        class Queue:
            def put(self, value):
                pass

        class CancelEvent:
            def is_set(self):
                return False

        class Model:
            captured = None

            async def astream(self, messages):
                self.captured = messages
                yield AIMessageChunk(content="完成")

        spec = WorkerSpec(
            run_id="run",
            workflow_id="visual-flow",
            artifact_paths={},
            dependencies={"visual-flow": {"child": "child-flow"}},
            inputs={"message": "hello"},
            permission_mode="manual",
            recursion_limit=20,
        )
        model = Model()
        gateway = WorkerGateway(
            spec,
            EventEmitter(Queue(), "run"),
            CancelEvent(),
            run_id="run",
            workflow_id="visual-flow",
            parent_run_id=None,
            call_depth=0,
            call_stack=("visual-flow",),
        )
        agent = SimpleNamespace(enabled=True, model_profile_id="")
        with (
            patch("my_agent_next.app.workflows.worker.AgentProfileRepository.get", return_value=agent),
            patch("my_agent_next.app.workflows.worker.ChatService.resolve_model_or_raise", return_value=object()),
            patch("my_agent_next.app.workflows.worker.build_agent_context_messages", return_value=([SystemMessage(content="persona")], [])),
            patch("my_agent_next.app.workflows.worker._build_model", return_value=model),
        ):
            result = await gateway._run_agent(
                "mabel",
                {"message": "do work"},
                step_id="mabel_works",
                route="- START -> mabel_works\n- mabel_works -> END",
            )
        self.assertEqual(result, {"answer": "完成"})
        system_text = "\n".join(
            message.content for message in model.captured
            if isinstance(message, SystemMessage)
        )
        self.assertIn("你当前所在步骤：mabel_works", system_text)
        self.assertIn("START -> mabel_works", system_text)


if __name__ == "__main__":
    unittest.main()
