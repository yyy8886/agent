"""Shared AgentRuntime behavior used by chat and workflow calls."""

import unittest

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from my_agent_next.app.agent_runtime import run_agent_runtime
from my_agent_next.app.chat_service import _message_text


class _ToolThenAnswerModel:
    def __init__(self):
        self.calls = 0

    async def astream(self, messages):
        self.calls += 1
        if self.calls == 1:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{
                    "name": "read_file",
                    "args": '{"path":"diagram.drawio"}',
                    "id": "call-1",
                    "index": 0,
                }],
            )
        else:
            yield AIMessageChunk(content="checked")


class _ReviewRetryModel:
    def __init__(self):
        self.calls = 0

    async def astream(self, messages):
        self.calls += 1
        text = "bad review" if self.calls == 1 else "valid review"
        yield AIMessageChunk(content=text)


class _RepeatingModel:
    async def astream(self, messages):
        for _ in range(8):
            yield AIMessageChunk(content="让我查看工作目录里的临时脚本。")


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_tool_loop_and_emits_same_events(self):
        events = []
        tools = []

        async def emit(event, data):
            events.append((event, data))

        async def execute_tool(name, arguments, call_id):
            tools.append((name, arguments, call_id))
            return "file contents"

        result = await run_agent_runtime(
            messages=[HumanMessage(content="inspect")],
            model=_ToolThenAnswerModel(),
            selected_skill_names=[],
            max_iterations=3,
            emit=emit,
            execute_tool=execute_tool,
            message_text=_message_text,
            validate_review=lambda text: True,
        )
        self.assertEqual(result.answer, "checked")
        self.assertEqual(tools[0][0], "read_file")
        self.assertEqual([item[0] for item in events], ["tool_call", "tool_result", "token"])

    async def test_review_contract_retries_inside_shared_runtime(self):
        events = []

        async def emit(event, data):
            events.append((event, data))

        async def unused_tool(name, arguments, call_id):
            raise AssertionError("tool should not run")

        result = await run_agent_runtime(
            messages=[HumanMessage(content="review")],
            model=_ReviewRetryModel(),
            selected_skill_names=["review-agent"],
            max_iterations=3,
            emit=emit,
            execute_tool=unused_tool,
            message_text=_message_text,
            validate_review=lambda text: text == "valid review",
        )
        self.assertEqual(result.answer, "valid review")
        self.assertEqual(events, [("token", {"text": "valid review"})])

    async def test_stops_substantial_repeated_stream_output(self):
        events = []

        async def emit(event, data):
            events.append((event, data))

        async def unused_tool(name, arguments, call_id):
            raise AssertionError("tool should not run")

        with self.assertRaisesRegex(RuntimeError, "连续重复输出"):
            await run_agent_runtime(
                messages=[HumanMessage(content="inspect")],
                model=_RepeatingModel(),
                selected_skill_names=[],
                max_iterations=3,
                emit=emit,
                execute_tool=unused_tool,
                message_text=_message_text,
                validate_review=lambda text: True,
            )
        emitted = "".join(data["text"] for event, data in events if event == "token")
        self.assertLess(len(emitted), 100)


if __name__ == "__main__":
    unittest.main()
