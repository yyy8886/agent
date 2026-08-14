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
import re
from pathlib import Path

import yaml
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .agent_profile_repository import AgentProfileRepository
from .agent_profile import SKILL_NAME_PATTERN
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

SKILL_TOOL_ALLOWLISTS = {
    "review-agent": {"read_file", "grep", "glob"},
}

# 手动模式下等待用户确认的暂存区
_pending: dict[str, asyncio.Event] = {}
_decisions: dict[str, dict] = {}

# ask_user_question 等待区
_question_pending: dict[str, asyncio.Event] = {}
_question_answers: dict[str, dict] = {}


def build_agent_context_messages(agent, user_content: str) -> tuple[list, list[str]]:
    """Build the shared persona, persisted Skill, and memory context for an Agent."""
    messages = []
    selected_skill_names: list[str] = []
    if agent is None:
        return messages, selected_skill_names

    parts = []
    if agent.name:
        parts.append(f"你的名字是{agent.name}。")
    if agent.persona:
        parts.append(agent.persona)
    if parts:
        messages.append(SystemMessage(content=" ".join(parts)))

    from my_agent_next.skills._loader import get as get_skill
    from my_agent_next.skills._router import SkillRouter, build_skill_catalog

    skills_dir = Path(__file__).resolve().parent.parent / "skills"
    bound_skills = agent.skills or []
    catalog = build_skill_catalog(bound_skills)
    if catalog:
        messages.append(SystemMessage(content=(
            "## 已授权 Skill 目录\n"
            "以下仅表示该 Agent 有权使用；未加载正文的 Skill 不得声称已经执行。\n"
            f"{catalog}"
        )))

    selected_routes = SkillRouter().select(user_content, bound_skills)
    selected_skill_names = [route.name for route in selected_routes]
    for route in selected_routes:
        info = get_skill(route.name)
        if info is None:
            continue
        skill_dir = skills_dir / route.name
        scripts_list = []
        refs_list = []
        if skill_dir.is_dir():
            scripts_dir = skill_dir / "scripts"
            if scripts_dir.is_dir():
                scripts_list = sorted(
                    path.name for path in scripts_dir.iterdir()
                    if path.is_file() and not path.name.startswith(".")
                )
            refs_dir = skill_dir / "references"
            if refs_dir.is_dir():
                refs_list = sorted(
                    path.name for path in refs_dir.iterdir()
                    if path.is_file() and not path.name.startswith(".")
                )
        resources_note = ""
        if scripts_list or refs_list:
            resources_note = f"\n\n## Skill 资源清单（位于 skills/{route.name}/）\n"
            if scripts_list:
                resources_note += "\n### scripts/ — 用 run_bash 执行：\n" + "\n".join(
                    f"- `python skills/{route.name}/scripts/{script}`" for script in scripts_list
                )
            if refs_list:
                resources_note += "\n\n### references/ — 用 read_file 查阅：\n" + "\n".join(
                    f"- `skills/{route.name}/references/{reference}`" for reference in refs_list
                )
        messages.append(SystemMessage(content=(
            f"## 本轮已加载 Skill：{info.name}\n"
            f"路由原因：{route.reason}\n"
            f"Skill 文件目录：skills/{route.name}/\n\n"
            f"{info.description}\n\n{info.content}{resources_note}"
        )))

    if "user-memory" in bound_skills:
        from .user_memory_service import UserMemoryService
        memory_prompt = UserMemoryService().get_memory_prompt()
        if memory_prompt:
            messages.append(SystemMessage(content=memory_prompt))
    return messages, selected_skill_names


def set_tool_decision(thread_id: str, tool_call_id: str, allowed: bool) -> None:
    """由 chat_api 调用，存入用户对工具调用的决定。"""
    key = f"{thread_id}:{tool_call_id}"
    _decisions[key] = {"allowed": allowed}
    event = _pending.get(key)
    if event:
        event.set()


def set_question_response(thread_id: str, call_id: str, answers: list) -> None:
    """由 chat_api 调用，存入用户对 ask_user_question 的答案。"""
    key = f"{thread_id}:{call_id}"
    _question_answers[key] = {"answers": answers}
    event = _question_pending.get(key)
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

        messages, _ = build_agent_context_messages(agent, user_content)

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
        # 获取 agent
        agent_repo = AgentProfileRepository()
        agent = agent_repo.get(agent_id)
        messages = self.build_messages(agent_id, thread_id, user_content)

        selected_skill_names: list[str] = []
        if agent:
            from my_agent_next.skills._router import SkillRouter
            selected_skill_names = [
                route.name for route in SkillRouter().select(user_content, agent.skills or [])
            ]
        allowed_tool_names = _tool_names_for_skills(selected_skill_names)
        model = _build_model(profile, allowed_tool_names=allowed_tool_names)
        skill_directories_before = (
            _indexed_skill_directories()
            if "skill-creator" in selected_skill_names else set()
        )

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
        review_format_retry_used = False

        for iteration in range(MAX_AGENT_ITERATIONS):
            try:
                response = None
                hold_for_review = "review-agent" in selected_skill_names
                async for chunk in model.astream(messages):
                    response = chunk if response is None else response + chunk
                    chunk_text = _message_text(chunk)
                    if chunk_text:
                        if not hold_for_review:
                            yield f"data: {json.dumps({'token': chunk_text})}\n\n"
                if response is None:
                    raise RuntimeError("模型没有返回任何内容")
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)[:500]})}\n\n"
                return

            # 检查是否有工具调用
            if hasattr(response, "tool_calls") and response.tool_calls:
                tool_calls = response.tool_calls
                content = _message_text(response)

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

                    # ── ask_user_question 拦截 ──────────────────────
                    if tool_name == "ask_user_question":
                        questions_str = str(tool_args.get("questions_json", ""))
                        try:
                            questions = json.loads(questions_str)
                        except json.JSONDecodeError:
                            questions = [{"question": questions_str, "header": "问题", "options": [], "multiSelect": False}]

                        question_key = f"{thread_id}:{tc_id}"
                        yield f"data: {json.dumps({'event': 'ask_user', 'data': {'call_id': tc_id, 'questions': questions}})}\n\n"

                        # 等待用户回答
                        event = asyncio.Event()
                        _question_pending[question_key] = event
                        try:
                            await asyncio.wait_for(event.wait(), timeout=300.0)
                        except asyncio.TimeoutError:
                            _question_pending.pop(question_key, None)
                            answer_text = "用户未在超时时间内回答。"
                        else:
                            _question_pending.pop(question_key, None)
                            answer_data = _question_answers.pop(question_key, {})
                            answers = answer_data.get("answers", [])
                            answer_text = json.dumps(answers, ensure_ascii=False)

                        messages.append(ToolMessage(
                            content=answer_text,
                            tool_call_id=tc_id,
                        ))
                        yield f"data: {json.dumps({'event': 'tool_result', 'data': {'name': tool_name, 'result': answer_text[:500]}})}\n\n"
                        continue

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
                    result = await self._execute_tool(tool_name, tool_args)

                    newly_bound = []
                    if "skill-creator" in selected_skill_names:
                        newly_bound = _bind_newly_created_skills(
                            agent_id, skill_directories_before
                        )
                        skill_directories_before.update(newly_bound)
                        if newly_bound:
                            result = (
                                f"{result}\n已自动绑定到当前 Agent："
                                + "、".join(newly_bound)
                            )
                            for skill_name in newly_bound:
                                yield f"data: {json.dumps({'event': 'skill', 'data': {'name': skill_name, 'summary': '已创建并自动绑定到当前 Agent'}})}\n\n"

                    yield f"data: {json.dumps({'event': 'tool_result', 'data': {'name': tool_name, 'result': str(result)[:500]}})}\n\n"

                    messages.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tc_id,
                    ))

                # 继续循环，让 LLM 处理工具结果
                continue

            # 没有工具调用 → 最终文本回复
            text = _message_text(response)
            if "review-agent" in selected_skill_names and not _is_valid_review_response(text):
                if not review_format_retry_used:
                    review_format_retry_used = True
                    messages.append(AIMessage(content=str(text)))
                    messages.append(SystemMessage(content=(
                        "Your review result violated the required output contract. Rewrite only the "
                        "final answer now. Start with either '[P0]' through '[P3]' in the exact "
                        "'[P#] title — path:line' form, or 'No findings.'. End with exactly one "
                        "'Overall assessment:' line and one 'Test gaps or residual risks:' line. "
                        "Do not use headings, tables, emojis, scratch analysis, or call tools."
                    )))
                    continue
                yield f"data: {json.dumps({'error': 'review-agent returned an invalid final format after one correction attempt'})}\n\n"
                return
            if text:
                full_response += text
            # review-agent 的完整结果必须先通过格式校验；其他响应已在
            # model.astream() 产生内容块时实时发送。
            if hold_for_review:
                yield f"data: {json.dumps({'token': text})}\n\n"
            break

        else:
            # 达到最大迭代次数
            yield f"data: {json.dumps({'error': f'达到最大工具调用次数（{MAX_AGENT_ITERATIONS}）'})}\n\n"

        # ── 自动提取用户记忆（在 done 之前，让前端折叠栏能展示） ──
        if agent and "user-memory" in (agent.skills or []) and full_response:
            from .user_memory_service import UserMemoryService
            try:
                saved = UserMemoryService().extract_and_save(
                    user_content, full_response, profile
                )
                if saved:
                    print(f"[Memory] 提取到 {len(saved)} 条新记忆: {saved}")
                    saved_text = '；'.join(str(s) for s in saved)
                    if len(saved_text) > 120:
                        saved_text = saved_text[:120] + '…'
                    yield f"data: {json.dumps({'event': 'skill', 'data': {'name': 'user-memory', 'summary': f'提取到 {len(saved)} 条新记忆：{saved_text}'}})}\n\n"
            except Exception:
                pass

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

    @staticmethod
    async def _execute_tool(tool_name: str, tool_args: dict) -> str:
        """执行工具并返回结果。

        工具（尤其是 run_bash 的 subprocess.run）是同步阻塞调用，若在 async
        生成器里直接执行会卡死整个事件循环（表现为所有请求超时、前端流中断）。
        这里放到线程池执行，避免阻塞事件循环。
        """
        tool = TOOL_BY_NAME.get(tool_name)
        if not tool:
            return f"未知工具：{tool_name}"
        try:
            result = await asyncio.to_thread(tool.invoke, tool_args)
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


def _message_text(message) -> str:
    """Normalize text from LangChain message and message-chunk content."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content) if content is not None else ""


def _tool_names_for_skills(selected_skill_names: list[str]) -> set[str] | None:
    """Return an enforced tool allowlist when an active Skill requires one."""
    restricted = [
        SKILL_TOOL_ALLOWLISTS[name]
        for name in selected_skill_names
        if name in SKILL_TOOL_ALLOWLISTS
    ]
    if not restricted:
        return None
    return set.intersection(*restricted)


def _indexed_skill_directories() -> set[str]:
    from my_agent_next.skills._loader import ensure_index

    return {str(item["directory"]) for item in ensure_index()["skills"]}


def _bind_newly_created_skills(
    agent_id: str,
    directories_before: set[str],
    repository: AgentProfileRepository | None = None,
) -> list[str]:
    """Bind valid Skill directories first indexed during this creator run."""
    repository = repository or AgentProfileRepository()
    candidates = sorted(_indexed_skill_directories() - directories_before)
    return [
        name for name in candidates
        if SKILL_NAME_PATTERN.fullmatch(name) and repository.add_skill(agent_id, name)
    ]


def _is_valid_review_response(text: str) -> bool:
    """Validate the externally visible review-agent response contract."""
    stripped = str(text).strip()
    if not stripped:
        return False
    first_line = stripped.splitlines()[0].strip()
    valid_start = first_line == "No findings." or bool(
        re.fullmatch(r"\[P[0-3]\] .+ — .+:\d+", first_line)
    )
    return (
        valid_start
        and len(re.findall(r"(?m)^Overall assessment: .+$", stripped)) == 1
        and len(re.findall(r"(?m)^Test gaps or residual risks: .+$", stripped)) == 1
    )


def _build_model(profile, allowed_tool_names: set[str] | None = None):
    """根据 ApiProfile 创建 LangChain ChatModel，并绑定工具。"""
    tools = (
        [tool for tool in ALL_TOOLS if tool.name in allowed_tool_names]
        if allowed_tool_names is not None else ALL_TOOLS
    )
    common = {"model": profile.model, "temperature": profile.temperature}
    if profile.provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        model = ChatDeepSeek(**common, api_key=os.getenv(profile.api_key_env or ""),
                             base_url=profile.base_url or "https://api.deepseek.com",
                             timeout=profile.timeout_seconds,
                             max_retries=profile.max_retries)
        return model.bind_tools(tools)
    elif profile.provider == "openai":
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(**common, api_key=os.getenv(profile.api_key_env or ""),
                           base_url=profile.base_url or "https://api.openai.com/v1",
                           timeout=profile.timeout_seconds,
                           max_retries=profile.max_retries)
        return model.bind_tools(tools)
    elif profile.provider == "ollama":
        from langchain_ollama import ChatOllama
        model = ChatOllama(**common,
                           base_url=profile.base_url or "http://127.0.0.1:11434")
        return model.bind_tools(tools)
    raise ValueError(f"不支持的 provider：{profile.provider}")
