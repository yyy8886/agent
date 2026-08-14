"""Integration tests for direct LangGraph artifacts and worker cancellation."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from my_agent_next.app.workflows.artifact import WorkflowArtifactStore
from my_agent_next.app.workflows.model import WorkflowDraft
from my_agent_next.app.workflows.repository import WorkflowRepository
from my_agent_next.app.workflows.run_manager import WorkflowRunManager
from my_agent_next.app.workflows.worker import _redact_value


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


if __name__ == "__main__":
    unittest.main()
