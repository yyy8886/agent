"""Regression tests for model-level streaming in the chat service."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk

from my_agent_next.app.chat_service import ChatService


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


class _StreamingModel:
    async def astream(self, _messages):
        yield AIMessageChunk(content="第一块")
        await asyncio.sleep(0)
        yield AIMessageChunk(content="第二块")


class ChatStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_forwards_model_chunks_without_rechunking(self):
        repo = _Repository()
        agent = SimpleNamespace(skills=[], persona="", name="Test Agent")

        with (
            patch("my_agent_next.app.chat_service.AgentProfileRepository.get", return_value=agent),
            patch("my_agent_next.app.chat_service._build_model", return_value=_StreamingModel()),
        ):
            events = []
            async for raw in ChatService(repo).stream_chat(
                "agent", "thread", "hello", SimpleNamespace(), permission_mode="auto"
            ):
                events.append(json.loads(raw.removeprefix("data: ").strip()))

        self.assertEqual(
            [event["token"] for event in events if "token" in event],
            ["第一块", "第二块"],
        )
        self.assertEqual(repo.saved[-1], ("thread", "assistant", "第一块第二块"))
        self.assertTrue(events[-1].get("done"))


if __name__ == "__main__":
    unittest.main()
