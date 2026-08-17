"""Regression tests for durable chat terminal states."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk

from my_agent_next.app.chat_service import ChatService


class _Repository:
    def __init__(self):
        self.saved = []

    def get_messages(self, _thread_id, limit=None):
        messages = [
            SimpleNamespace(role=role, content=content)
            for _thread, role, content in self.saved
        ]
        return messages[-limit:] if limit else messages

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


class _EmptyModel:
    async def astream(self, _messages):
        yield AIMessageChunk(content="")


class _FailingModel:
    async def astream(self, _messages):
        raise RuntimeError("provider failed")
        yield


class _HangingModel:
    async def astream(self, _messages):
        await asyncio.Event().wait()
        yield


class ChatTerminalStatusTests(unittest.IsolatedAsyncioTestCase):
    def _patches(self, temporary, model):
        agent = SimpleNamespace(skills=[], persona="", name="Test Agent")
        return (
            patch(
                "my_agent_next.app.agent_run_log.DEFAULT_LOG_ROOT",
                Path(temporary),
            ),
            patch(
                "my_agent_next.app.chat_service.AgentProfileRepository.get",
                return_value=agent,
            ),
            patch(
                "my_agent_next.app.chat_service._build_model",
                return_value=model,
            ),
        )

    async def test_persists_runtime_failure(self):
        repo = _Repository()
        with tempfile.TemporaryDirectory() as temporary:
            first, second, third = self._patches(temporary, _FailingModel())
            with first, second, third:
                events = [
                    json.loads(raw.removeprefix("data: ").strip())
                    async for raw in ChatService(repo).stream_chat(
                        "agent", "thread", "hello", SimpleNamespace(),
                        permission_mode="auto",
                    )
                ]
        self.assertIn("provider failed", events[-1]["error"])
        self.assertIn("[运行失败，可继续]", repo.saved[-1][2])
        self.assertIn("执行现场", repo.saved[-1][2])

    async def test_persists_empty_answer(self):
        repo = _Repository()
        with tempfile.TemporaryDirectory() as temporary:
            first, second, third = self._patches(temporary, _EmptyModel())
            with first, second, third:
                async for _ in ChatService(repo).stream_chat(
                    "agent", "thread", "hello", SimpleNamespace(),
                    permission_mode="auto",
                ):
                    pass
        self.assertIn("[运行结束但未产生输出]", repo.saved[-1][2])

    async def test_persists_cancelled_run(self):
        repo = _Repository()

        async def consume():
            async for _ in ChatService(repo).stream_chat(
                "agent", "thread", "hello", SimpleNamespace(),
                permission_mode="auto",
            ):
                pass

        with tempfile.TemporaryDirectory() as temporary:
            first, second, third = self._patches(temporary, _HangingModel())
            with first, second, third:
                task = asyncio.create_task(consume())
                await asyncio.sleep(0.02)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                with patch(
                    "my_agent_next.app.chat_service.AgentProfileRepository.list",
                    return_value=[],
                ):
                    next_messages = ChatService(repo).build_messages(
                        "agent", "thread", "continue",
                    )
        self.assertIn("[运行已取消，可继续]", repo.saved[-1][2])
        self.assertIn("执行现场", repo.saved[-1][2])
        self.assertTrue(any(
            "[运行已取消，可继续]" in str(message.content)
            for message in next_messages
        ))


if __name__ == "__main__":
    unittest.main()
