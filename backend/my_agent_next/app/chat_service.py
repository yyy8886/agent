# chat_service.py — 对话业务逻辑层
# =============================================================================
# 本文件负责对话编排：构建消息列表、流式调用 LLM、触发 compact。
# 它是 chat_api.py（接口层）和 chat_repository.py（数据层）之间的中间层。
#
# 职责：
#   1. resolve_model(agent)        — 确定 Agent 绑定的模型（空则取默认）
#   2. build_messages(agent,...)    — 组装 system(persona/摘要) + 历史 + 新消息
#   3. stream_chat(profile,...)     — 异步流式调用 LLM，保存消息，触发 compact
#
# 项目中的位置（三层架构）：
#   chat_api.py → ChatService → ChatRepository
#   SSE 端点     → 业务编排    → SQLite"""

import os
import json
from pathlib import Path

import yaml

from .agent_profile_repository import AgentProfileRepository
from .api_profile_repository import ApiProfileRepository
from .chat_repository import ChatRepository

_config_path = Path(__file__).resolve().parent.parent / "config.yaml"
with open(_config_path, "r", encoding="utf-8") as f:
    _chat_config = yaml.safe_load(f).get("chat", {})

MAX_CONTEXT = _chat_config.get("max_context_messages", 20)
KEEP_RECENT = _chat_config.get("keep_recent_on_compact", 8)
MAX_PER_THREAD = _chat_config.get("max_messages_per_thread", 500)


class ChatService:
    def __init__(self, repository: ChatRepository | None = None):
        self.repo = repository or ChatRepository()

    # ── 模型解析 ──────────────────────────────────────────────────────────

    @staticmethod
    def resolve_model(agent_model_profile_id: str):
        """根据 Agent 的 model_profile_id 获取 API 配置，为空则用默认。"""
        api_repo = ApiProfileRepository()
        if agent_model_profile_id:
            profile = api_repo.get(agent_model_profile_id)
            if profile and profile.enabled:
                return profile
        # fallback 到默认
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
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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

        # 2. Compact 摘要（排在 persona 之后、历史之前）
        summary = (self.repo.get_thread(thread_id) or {}).get("summary", "")
        if summary:
            messages.append(SystemMessage(content=f"[历史摘要] {summary}"))

        # 3. 最近的历史消息
        history = self.repo.get_messages(thread_id, limit=MAX_CONTEXT)
        for m in history:
            if m.role == "user":
                messages.append(HumanMessage(content=m.content))
            else:
                messages.append(AIMessage(content=m.content))

        # 4. 当前用户消息
        messages.append(HumanMessage(content=user_content))

        return messages

    # ── 流式对话 ──────────────────────────────────────────────────────────

    async def stream_chat(self, agent_id: str, thread_id: str,
                          user_content: str, profile):
        """异步生成器：流式调用 LLM，yield SSE data，结束时存消息+compact。"""
        messages = self.build_messages(agent_id, thread_id, user_content)
        model = _build_model(profile)

        # 存用户消息
        self.repo.save_message(thread_id, "user", user_content)
        self.repo.touch_thread(thread_id)

        # 自动标题
        thread = self.repo.get_thread(thread_id)
        if thread and not thread.get("title"):
            self.repo.update_thread_title(thread_id, user_content[:40])

        full_response = ""
        try:
            async for chunk in model.astream(messages):
                text = chunk.content if hasattr(chunk, "content") else str(chunk)
                if text:
                    full_response += text
                    yield f"data: {json.dumps({'token': text})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)[:500]})}\n\n"
            return

        # 流结束
        yield f"data: {json.dumps({'done': True})}\n\n"

        # 存 AI 回复
        if full_response:
            self.repo.save_message(thread_id, "assistant", full_response)
            self.repo.touch_thread(thread_id)

        # DB 硬上限
        self.repo.enforce_message_limit(thread_id, MAX_PER_THREAD)

        # 自动 compact
        self._auto_compact(thread_id, profile)

    def _auto_compact(self, thread_id: str, profile) -> None:
        """如果线程消息超过阈值，自动压缩旧消息为摘要。"""
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
            pass  # compact 失败不影响主流程


def _build_model(profile):
    """根据 ApiProfile 创建对应的 LangChain ChatModel。"""
    common = {"model": profile.model, "temperature": profile.temperature}
    if profile.provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(**common, api_key=os.getenv(profile.api_key_env or ""),
                            base_url=profile.base_url or "https://api.deepseek.com",
                            timeout=profile.timeout_seconds, max_retries=profile.max_retries)
    elif profile.provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(**common, api_key=os.getenv(profile.api_key_env or ""),
                          base_url=profile.base_url or "https://api.openai.com/v1",
                          timeout=profile.timeout_seconds, max_retries=profile.max_retries)
    elif profile.provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(**common, base_url=profile.base_url or "http://127.0.0.1:11434")
    raise ValueError(f"不支持的 provider：{profile.provider}")
