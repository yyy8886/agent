"""Runtime Skill discovery stays dynamic and respects Agent bindings."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk, SystemMessage, ToolMessage

from my_agent_next.app.chat_service import ChatService
from my_agent_next.app.tools import TOOL_BY_NAME
from my_agent_next.app.tools.skill_discovery import (
    discover_authorized_skills,
    load_authorized_skill,
)
from my_agent_next.app.workflows.worker import EventEmitter, WorkerGateway, WorkerSpec


class _Repository:
    def __init__(self):
        self.saved = []

    def get_messages(self, _thread_id, limit=None):
        return []

    def save_message(self, thread_id, role, content):
        self.saved.append((thread_id, role, content))

    def touch_thread(self, _thread_id):
        pass

    def get_thread(self, _thread_id):
        return {"title": "existing"}

    def enforce_message_limit(self, _thread_id, _limit):
        pass

    def should_compact(self, _thread_id, _limit):
        return False


class _LoadSkillThenAnswerModel:
    def __init__(self):
        self.calls = 0
        self.second_messages = None

    async def astream(self, messages):
        self.calls += 1
        if self.calls == 1:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{
                    "name": "load_skill",
                    "args": '{"name":"drawio-skill"}',
                    "id": "load-1",
                    "index": 0,
                }],
            )
            return
        self.second_messages = list(messages)
        yield AIMessageChunk(content="runtime skill applied")


class RuntimeSkillDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_tools_are_registered_for_models(self):
        self.assertIn("discover_skills", TOOL_BY_NAME)
        self.assertIn("load_skill", TOOL_BY_NAME)

    def test_discovery_does_not_expose_unbound_skills(self):
        result = discover_authorized_skills(
            "diagram and environment", ["drawio-skill"]
        )
        self.assertIn("drawio-skill", result)
        self.assertNotIn("environment-memory", result)

    def test_loading_unbound_skill_is_denied(self):
        result = load_authorized_skill("drawio-skill", ["user-memory"])
        self.assertIn("Permission denied", result)

    async def test_chat_can_load_bound_skill_after_the_first_model_turn(self):
        repo = _Repository()
        model = _LoadSkillThenAnswerModel()
        agent = SimpleNamespace(
            id="mabel",
            name="Mabel",
            persona="",
            skills=["drawio-skill"],
        )
        with (
            patch("my_agent_next.app.chat_service.AgentProfileRepository.get", return_value=agent),
            patch("my_agent_next.app.chat_service.AgentProfileRepository.list", return_value=[]),
            patch("my_agent_next.app.chat_service._build_model", return_value=model),
        ):
            events = []
            async for raw in ChatService(repo).stream_chat(
                "mabel", "thread", "inspect this", SimpleNamespace(),
                permission_mode="auto",
            ):
                events.append(json.loads(raw.removeprefix("data: ").strip()))

        self.assertEqual(repo.saved[-1], ("thread", "assistant", "runtime skill applied"))
        self.assertTrue(any(event.get("event") == "skill" for event in events))
        tool_messages = [
            message for message in model.second_messages
            if isinstance(message, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("Skill loaded: drawio-skill", tool_messages[0].content)

    async def test_workflow_agent_can_load_bound_skill_during_its_run(self):
        class Queue:
            def __init__(self):
                self.items = []

            def put(self, item):
                self.items.append(item)

        class CancelEvent:
            @staticmethod
            def is_set():
                return False

        queue = Queue()
        model = _LoadSkillThenAnswerModel()
        agent = SimpleNamespace(
            id="mabel",
            enabled=True,
            model_profile_id="",
            skills=["drawio-skill"],
        )
        spec = WorkerSpec(
            run_id="run",
            workflow_id="flow",
            artifact_paths={},
            dependencies={"flow": {}},
            inputs={"message": "inspect this"},
            permission_mode="auto",
            recursion_limit=20,
        )
        gateway = WorkerGateway(
            spec,
            EventEmitter(queue, "run"),
            CancelEvent(),
            run_id="run",
            workflow_id="flow",
            parent_run_id=None,
            call_depth=0,
            call_stack=("flow",),
        )
        with (
            patch("my_agent_next.app.workflows.worker.AgentProfileRepository.get", return_value=agent),
            patch("my_agent_next.app.workflows.worker.ChatService.resolve_model_or_raise", return_value=object()),
            patch(
                "my_agent_next.app.workflows.worker.build_agent_context_messages",
                return_value=([SystemMessage(content="persona")], []),
            ),
            patch("my_agent_next.app.workflows.worker._build_model", return_value=model),
        ):
            result = await gateway._run_agent(
                "mabel", {"message": "inspect this"}, step_id="work", route="START -> work"
            )

        self.assertEqual(result, {"answer": "runtime skill applied"})
        self.assertTrue(any(
            item["event"] == "agent_skill_loaded"
            and item["data"].get("runtime") is True
            for item in queue.items
        ))
        tool_messages = [
            message for message in model.second_messages
            if isinstance(message, ToolMessage)
        ]
        self.assertIn("Skill loaded: drawio-skill", tool_messages[0].content)


if __name__ == "__main__":
    unittest.main()
