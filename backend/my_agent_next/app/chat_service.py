# chat_service.py — 对话业务逻辑层（Agent 循环版本）
# =============================================================================
# 本文件负责对话编排，支持工具调用（tool calling）和三级权限控制。
#
# 职责：
#   1. resolve_model(agent)        — 确定 Agent 绑定的模型（空则取默认）
#   2. build_messages(agent,...)    — 组装 system(persona/摘要/Skill) + 历史 + 新消息
#   3. stream_chat(profile,...)     — Agent 循环：LLM ↔ 工具执行，SSE 流式返回
#
# 项目中的位置（三层架构）：
#   chat_api.py → ChatService → ChatRepository
#   SSE 端点     → 业务编排    → SQLite
# =============================================================================

import asyncio
import json
import os
from pathlib import Path

import yaml
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .agent_profile_repository import AgentProfileRepository
from .api_profile_repository import ApiProfileRepository
from .chat_repository import ChatRepository
from .tools import ALL_TOOLS, TOOL_BY_NAME
from .tools.base import PermissionMode, is_dangerous_command

_config_path = Path(__file__).resolve().parent.parent / "config.yaml"
with open(_config_path, "r", encoding="utf-8") as f:
    _chat_config = yaml.safe_load(f).get("chat", {})

MAX_CONTEXT = _chat_config.get("max_context_messages", 20)
KEEP_RECENT = _chat_config.get("keep_recent_on_compact", 8)
MAX_PER_THREAD = _chat_config.get("max_messages_per_thread", 500)
MAX_AGENT_ITERATIONS = _chat_config.get("max_agent_iterations", 10)

# 手动模式下等待用户确认的暂存区
_pending: dict[str, asyncio.Event] = {}
_decisions: dict[str, dict] = {}


def set_tool_decision(thread_id: str, tool_call_id: str, allowed: bool) -> None:
    """由 chat_api 调用，存入用户对工具调用的决定。"""
    key = f"{thread_id}:{tool_call_id}"
    _decisions[key] = {"allowed": allowed}
    event = _pending.get(key)
    if event:
        event.set()


class ChatService:
    def __init__(self, repository: ChatRepository | None = None):
        self.repo = repository or ChatRepository()

    # ── 模型解析 ──────────────────────────────────────────────────────────

    @staticmethod
    def resolve_model(agent_model_profile_id: str):
        api_repo = ApiProfileRepository()
        if agent_model_profile_id:
            profile = api_repo.get(agent_model_profile_id)
            if profile and profile.enabled:
                return profile
        for p in api_repo.list():
            if p.enabled and p.is_default:
                return p
        return None

    @staticmethod
    def resolve_model_or_raise(agent_model_profile_id: str):
        profile = ChatService.resolve_model(agent_model_profile_id)
        if not profile:
            raise ValueError("未绑定模型且没有启用的默认配置。")
        return profile

    # ── 消息构建 ──────────────────────────────────────────────────────────

    def build_messages(self, agent_id: str, thread_id: str,
                       user_content: str) -> list:
        """构建发给 LLM 的完整消息列表。"""
        agent_repo = AgentProfileRepository()
        agent = agent_repo.get(agent_id)

        persona = agent.persona if agent else ""
        name = agent.name if agent else ""

        messages = []

        # 1. Agent 人设（名字 + persona）
        if name or persona:
            parts = []
            if name:
                parts.append(f"你的名字是{name}。")
            if persona:
                parts.append(persona)
            messages.append(SystemMessage(content=" ".join(parts)))

        # 2. 注入 Agent 启用的 Skill 的 SKILL.md 内容
        if agent:
            from my_agent_next.skills._loader import get as get_skill
            for skill_name in agent.skills or []:
                info = get_skill(skill_name)
                if info:
                    skill_prompt = (
                        f"## 可用技能：{info.name}\n\n"
                        f"{info.description}\n\n{info.content}"
                    )
                    messages.append(SystemMessage(content=skill_prompt))

        # 3. 用户记忆注入（user-memory Skill 的代码后台）
        if agent and "user-memory" in (agent.skills or []):
            from .user_memory_service import UserMemoryService
            mem_prompt = UserMemoryService().get_memory_prompt()
            if mem_prompt:
                messages.append(SystemMessage(content=mem_prompt))

        # 4. Compact 摘要
        summary = (self.repo.get_thread(thread_id) or {}).get("summary", "")
        if summary:
            messages.append(SystemMessage(content=f"[历史摘要] {summary}"))

        # 5. 最近的历史消息
        history = self.repo.get_messages(thread_id, limit=MAX_CONTEXT)
        for m in history:
            if m.role == "user":
                messages.append(HumanMessage(content=m.content))
            else:
                messages.append(AIMessage(content=m.content))

        # 6. 当前用户消息
        messages.append(HumanMessage(content=user_content))

        return messages

    # ── Agent 循环（工具调用 + 权限控制）──────────────────────────────────

    async def stream_chat(self, agent_id: str, thread_id: str,
                          user_content: str, profile,
                          permission_mode: str = "manual"):
        """Agent 循环：LLM ↔ 工具执行，SSE 流式返回。"""
        messages = self.build_messages(agent_id, thread_id, user_content)
        model = _build_model(profile)

        # 获取 agent
        agent_repo = AgentProfileRepository()
        agent = agent_repo.get(agent_id)

        # 存用户消息
        self.repo.save_message(thread_id, "user", user_content)
        self.repo.touch_thread(thread_id)

        # 自动标题
        thread = self.repo.get_thread(thread_id)
        if thread and not thread.get("title"):
            self.repo.update_thread_title(thread_id, user_content[:40])

        # ── Agent 循环 ──────────────────────────────────────────────────
        full_response = ""
        tool_calls_log: list[dict] = []

        for iteration in range(MAX_AGENT_ITERATIONS):
            try:
                response = await model.ainvoke(messages)
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)[:500]})}\n\n"
                return

            # 检查是否有工具调用
            if hasattr(response, "tool_calls") and response.tool_calls:
                tool_calls = response.tool_calls
                content = response.content if hasattr(response, "content") else ""

                # 添加 AI 消息到历史
                ai_msg = AIMessage(content=str(content) if content else "")
                if hasattr(ai_msg, "tool_calls"):
                    ai_msg.tool_calls = tool_calls
                messages.append(ai_msg)

                if content:
                    full_response += str(content)

                # 逐个执行工具调用
                for tc in tool_calls:
                    tool_name = tc.get("name", "")
                    tool_args = tc.get("args", {})
                    tc_id = tc.get("id", "")

                    tool_calls_log.append({"name": tool_name, "args": tool_args})

                    # 通知前端工具调用
                    yield f"data: {json.dumps({'event': 'tool_call', 'data': {'name': tool_name, 'args': tool_args}})}\n\n"

                    # ── 权限检查 ──────────────────────────────────────
                    allowed = True
                    if permission_mode == PermissionMode.MANUAL.value:
                        key = f"{thread_id}:{tc_id}"
                        is_dangerous = (
                            tool_name == "run_bash"
                            and is_dangerous_command(str(tool_args.get("command", "")))
                        )
                        # yield 确认事件
                        yield f"data: {json.dumps({'event': 'tool_confirm', 'data': {'confirm_id': tc_id, 'name': tool_name, 'args': tool_args, 'dangerous': is_dangerous}})}\n\n"
                        # 等待用户响应
                        event = asyncio.Event()
                        _pending[key] = event
                        try:
                            await asyncio.wait_for(event.wait(), timeout=120.0)
                        except asyncio.TimeoutError:
                            _pending.pop(key, None)
                            allowed = False
                        else:
                            _pending.pop(key, None)
                            decision = _decisions.pop(key, {})
                            allowed = decision.get("allowed", False)

                    elif permission_mode == PermissionMode.AUTO.value:
                        allowed = True

                    if not allowed:
                        messages.append(ToolMessage(
                            content="用户拒绝了此操作。请尝试其他方式或向用户解释。",
                            tool_call_id=tc_id,
                        ))
                        yield f"data: {json.dumps({'event': 'tool_result', 'data': {'name': tool_name, 'result': '用户拒绝', 'allowed': False}})}\n\n"
                        continue

                    # ── 执行工具 ──────────────────────────────────────
                    result = self._execute_tool(tool_name, tool_args)

                    yield f"data: {json.dumps({'event': 'tool_result', 'data': {'name': tool_name, 'result': str(result)[:500]}})}\n\n"

                    messages.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tc_id,
                    ))

                # 继续循环，让 LLM 处理工具结果
                continue

            # 没有工具调用 → 最终文本回复
            text = response.content if hasattr(response, "content") else str(response)
            if text:
                full_response += text
            # 流式输出最终文本
            for char in _chunk_text(text):
                yield f"data: {json.dumps({'token': char})}\n\n"
            break

        else:
            # 达到最大迭代次数
            yield f"data: {json.dumps({'error': f'达到最大工具调用次数（{MAX_AGENT_ITERATIONS}）'})}\n\n"

        # ── 结束 ──────────────────────────────────────────────────────
        yield f"data: {json.dumps({'done': True})}\n\n"

        # 存 AI 回复
        if full_response:
            self.repo.save_message(thread_id, "assistant", full_response)
            self.repo.touch_thread(thread_id)

        # DB 硬上限
        self.repo.enforce_message_limit(thread_id, MAX_PER_THREAD)

        # 自动 compact
        self._auto_compact(thread_id, profile)

        # 自动提取用户记忆
        if agent and "user-memory" in (agent.skills or []) and full_response:
            from .user_memory_service import UserMemoryService
            try:
                saved = UserMemoryService().extract_and_save(
                    user_content, full_response, profile
                )
                if saved:
                    print(f"[Memory] 提取到 {len(saved)} 条新记忆: {saved}")
            except Exception:
                pass

    @staticmethod
    def _execute_tool(tool_name: str, tool_args: dict) -> str:
        """执行工具并返回结果。"""
        tool = TOOL_BY_NAME.get(tool_name)
        if not tool:
            return f"未知工具：{tool_name}"
        try:
            result = tool.invoke(tool_args)
            return str(result)
        except Exception as exc:
            return f"工具执行错误：{exc}"

    # ── Compact ──────────────────────────────────────────────────────────

    def _auto_compact(self, thread_id: str, profile) -> None:
        if not self.repo.should_compact(thread_id, MAX_CONTEXT):
            return
        summary_text = self.repo.compact(thread_id, KEEP_RECENT)
        if not summary_text:
            return
        try:
            summary_model = _build_model(profile)
            result = summary_model.invoke(summary_text)
            self.repo.apply_compact(thread_id, result.content[:500], KEEP_RECENT)
        except Exception:
            pass


def _chunk_text(text: str, size: int = 4):
    """将文本按字符分块，模拟流式输出。"""
    for i in range(0, len(text), size):
        yield text[i:i + size]


def _build_model(profile):
    """根据 ApiProfile 创建 LangChain ChatModel，并绑定工具。"""
    common = {"model": profile.model, "temperature": profile.temperature}
    if profile.provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        model = ChatDeepSeek(**common, api_key=os.getenv(profile.api_key_env or ""),
                             base_url=profile.base_url or "https://api.deepseek.com",
                             timeout=profile.timeout_seconds,
                             max_retries=profile.max_retries)
        return model.bind_tools(ALL_TOOLS)
    elif profile.provider == "openai":
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(**common, api_key=os.getenv(profile.api_key_env or ""),
                           base_url=profile.base_url or "https://api.openai.com/v1",
                           timeout=profile.timeout_seconds,
                           max_retries=profile.max_retries)
        return model.bind_tools(ALL_TOOLS)
    elif profile.provider == "ollama":
        from langchain_ollama import ChatOllama
        model = ChatOllama(**common,
                           base_url=profile.base_url or "http://127.0.0.1:11434")
        return model.bind_tools(ALL_TOOLS)
    raise ValueError(f"不支持的 provider：{profile.provider}")
