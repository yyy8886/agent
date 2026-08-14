"""Shared model/tool loop used by chat threads and workflow workers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage


EmitCallback = Callable[[str, dict], Awaitable[None]]
ToolCallback = Callable[[str, dict, str], Awaitable[str]]
CancelCallback = Callable[[], None]
TextCallback = Callable[[object], str]
ReviewCallback = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class AgentRuntimeResult:
    answer: str
    tool_calls: tuple[dict, ...]
    iterations: int


async def run_agent_runtime(
    *,
    messages: list,
    model,
    selected_skill_names: list[str],
    max_iterations: int,
    emit: EmitCallback,
    execute_tool: ToolCallback,
    message_text: TextCallback,
    validate_review: ReviewCallback,
    check_cancelled: CancelCallback | None = None,
) -> AgentRuntimeResult:
    """Run one Agent to completion while delegating UI and permissions."""
    full_response = ""
    tool_calls_log: list[dict] = []
    review_retry_used = False
    hold_for_review = "review-agent" in selected_skill_names

    for iteration in range(1, max_iterations + 1):
        if check_cancelled:
            check_cancelled()
        response = None
        async for chunk in model.astream(messages):
            if check_cancelled:
                check_cancelled()
            response = chunk if response is None else response + chunk
            text = message_text(chunk)
            if text and not hold_for_review:
                await emit("token", {"text": text})
        if response is None:
            raise RuntimeError("模型没有返回任何内容")

        tool_calls = getattr(response, "tool_calls", None) or []
        if tool_calls:
            content = message_text(response)
            messages.append(AIMessage(content=content, tool_calls=tool_calls))
            if content:
                full_response += content
            for tool_call in tool_calls:
                if check_cancelled:
                    check_cancelled()
                name = str(tool_call.get("name", ""))
                arguments = tool_call.get("args", {}) or {}
                call_id = str(tool_call.get("id", ""))
                record = {"name": name, "args": arguments}
                tool_calls_log.append(record)
                await emit("tool_call", {**record, "call_id": call_id})
                result = await execute_tool(name, arguments, call_id)
                await emit(
                    "tool_result",
                    {"name": name, "result": str(result), "call_id": call_id},
                )
                messages.append(ToolMessage(content=str(result), tool_call_id=call_id))
            continue

        text = message_text(response)
        if hold_for_review and not validate_review(text):
            if review_retry_used:
                raise RuntimeError(
                    "review-agent returned an invalid final format after one correction attempt"
                )
            review_retry_used = True
            messages.append(AIMessage(content=text))
            messages.append(SystemMessage(content=(
                "Your review result violated the required output contract. Rewrite only the "
                "final answer now. Start with either '[P0]' through '[P3]' in the exact "
                "'[P#] title — path:line' form, or 'No findings.'. End with exactly one "
                "'Overall assessment:' line and one 'Test gaps or residual risks:' line. "
                "Do not use headings, tables, emojis, scratch analysis, or call tools."
            )))
            continue
        if text:
            full_response += text
        if hold_for_review and text:
            await emit("token", {"text": text})
        return AgentRuntimeResult(
            answer=full_response,
            tool_calls=tuple(tool_calls_log),
            iterations=iteration,
        )

    raise RuntimeError(f"达到最大工具调用次数（{max_iterations}）")
