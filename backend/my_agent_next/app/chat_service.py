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
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from .agent_runtime import run_agent_runtime
from .agent_run_log import AgentRunLog, redact_sensitive
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
MIN_AGENT_ITERATIONS = 1
MAX_CONFIGURABLE_AGENT_ITERATIONS = 200

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

    current_agent_id = str(getattr(agent, "id", "")).strip()
    collaborators = [
        item for item in AgentProfileRepository().list() if item.enabled
    ]
    if collaborators:
        lines = []
        for item in collaborators:
            marker = "（当前是你）" if item.id == current_agent_id else ""
            role = item.role.strip() or "未填写职责"
            lines.append(f"- {item.name}（ID: {item.id}）{marker}：{role[:160]}")
        messages.append(SystemMessage(content=(
            "## Agent 协作目录\n"
            "以下是本应用中已启用的 Agent 及职责。你可以据此理解分工，但普通对话中"
            "不得声称已经调用其他 Agent；只有工作流运行上下文或实际工具结果能证明"
            "协作已经发生。不要模仿其他 Agent 的人设。\n"
            + "\n".join(lines)
        )))

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
                          permission_mode: str = "manual",
                          max_agent_iterations: int = MAX_AGENT_ITERATIONS):
        """Agent 循环：LLM ↔ 工具执行，SSE 流式返回。"""
        if (
            not isinstance(max_agent_iterations, int)
            or isinstance(max_agent_iterations, bool)
            or not MIN_AGENT_ITERATIONS
            <= max_agent_iterations
            <= MAX_CONFIGURABLE_AGENT_ITERATIONS
        ):
            raise ValueError(
                "max_agent_iterations 必须在 1-200 之间。"
            )

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

        # AgentRuntime owns the model/tool loop. This layer only translates
        # runtime events into chat SSE and performs interactive permission I/O.
        runtime_events: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        partial_output = ""
        recovery_steps: list[str] = []
        run_log = AgentRunLog(
            agent_id=agent_id,
            thread_id=thread_id,
            user_content=user_content,
            max_iterations=max_agent_iterations,
        )

        async def emit(event: str, data: dict) -> None:
            nonlocal partial_output
            if event == "token":
                token_text = str(data.get("text", ""))
                partial_output = (partial_output + token_text)[-1200:]
                run_log.append_output(token_text)
            else:
                run_log.flush_output()
                run_log.write(event, data)
                if event == "tool_call" and len(recovery_steps) < 20:
                    name = str(data.get("name", "unknown"))
                    arguments = json.dumps(
                        redact_sensitive(data.get("args", {})),
                        ensure_ascii=False,
                        default=str,
                    )
                    recovery_steps.append(
                        f"- 调用 {name}：{arguments[:300]}"
                    )
                elif event == "tool_result" and recovery_steps:
                    result = str(data.get("result", "")).replace("\n", " ")
                    recovery_steps[-1] += f"；结果：{result[:300]}"
            await runtime_events.put((event, data))

        def recovery_message(status: str, detail: str) -> str:
            sections = [
                f"[{status}] {detail}",
                "以下是中断前保留的执行现场，后续可以据此继续，但必须先核验文件当前状态：",
            ]
            if recovery_steps:
                sections.append("已执行的工具步骤：\n" + "\n".join(recovery_steps))
            else:
                sections.append("尚未完成任何工具调用。")
            if partial_output.strip():
                sections.append(
                    "中断前的模型输出片段：\n" + partial_output.strip()
                )
            return "\n\n".join(sections)

        async def execute_tool(tool_name: str, tool_args: dict, call_id: str) -> str:
            if tool_name == "ask_user_question":
                questions_str = str(tool_args.get("questions_json", ""))
                try:
                    questions = json.loads(questions_str)
                except json.JSONDecodeError:
                    questions = [{
                        "question": questions_str,
                        "header": "问题",
                        "options": [],
                        "multiSelect": False,
                    }]
                question_key = f"{thread_id}:{call_id}"
                await emit("ask_user", {"call_id": call_id, "questions": questions})
                event = asyncio.Event()
                _question_pending[question_key] = event
                try:
                    await asyncio.wait_for(event.wait(), timeout=300.0)
                except asyncio.TimeoutError:
                    return "用户未在超时时间内回答。"
                finally:
                    _question_pending.pop(question_key, None)
                answer_data = _question_answers.pop(question_key, {})
                return json.dumps(answer_data.get("answers", []), ensure_ascii=False)

            allowed = True
            if permission_mode == PermissionMode.MANUAL.value:
                key = f"{thread_id}:{call_id}"
                dangerous = tool_name == "run_bash" and is_dangerous_command(
                    str(tool_args.get("command", ""))
                )
                await emit("tool_confirm", {
                    "confirm_id": call_id,
                    "name": tool_name,
                    "args": tool_args,
                    "dangerous": dangerous,
                })
                event = asyncio.Event()
                _pending[key] = event
                try:
                    await asyncio.wait_for(event.wait(), timeout=120.0)
                except asyncio.TimeoutError:
                    allowed = False
                else:
                    allowed = _decisions.pop(key, {}).get("allowed", False)
                finally:
                    _pending.pop(key, None)
            if not allowed:
                return "用户拒绝了此操作。请尝试其他方式或向用户解释。"

            result = await self._execute_tool(tool_name, tool_args)
            if "skill-creator" in selected_skill_names:
                newly_bound = _bind_newly_created_skills(
                    agent_id, skill_directories_before
                )
                skill_directories_before.update(newly_bound)
                if newly_bound:
                    result = f"{result}\n已自动绑定到当前 Agent：" + "、".join(newly_bound)
                    for skill_name in newly_bound:
                        await emit("skill", {
                            "name": skill_name,
                            "summary": "已创建并自动绑定到当前 Agent",
                        })
            return result

        runtime_task = asyncio.create_task(run_agent_runtime(
            messages=messages,
            model=model,
            selected_skill_names=selected_skill_names,
            max_iterations=max_agent_iterations,
            emit=emit,
            execute_tool=execute_tool,
            message_text=_message_text,
            validate_review=_is_valid_review_response,
        ))
        try:
            while not runtime_task.done() or not runtime_events.empty():
                try:
                    event, data = await asyncio.wait_for(runtime_events.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                if event == "token":
                    yield f"data: {json.dumps({'token': data.get('text', '')})}\n\n"
                elif event == "tool_call":
                    yield f"data: {json.dumps({'event': 'tool_call', 'data': {'name': data.get('name', ''), 'args': data.get('args', {})}})}\n\n"
                elif event == "tool_result":
                    yield f"data: {json.dumps({'event': 'tool_result', 'data': {'name': data.get('name', ''), 'result': str(data.get('result', ''))[:500]}})}\n\n"
                else:
                    yield f"data: {json.dumps({'event': event, 'data': data})}\n\n"
            runtime_result = await runtime_task
            full_response = runtime_result.answer
            run_log.finish(
                "run_completed",
                iterations=runtime_result.iterations,
                tool_call_count=len(runtime_result.tool_calls),
                has_answer=bool(full_response),
            )
        except asyncio.CancelledError:
            if not runtime_task.done():
                runtime_task.cancel()
            run_log.finish("run_cancelled", reason="request_cancelled")
            self.repo.save_message(
                thread_id,
                "assistant",
                recovery_message(
                    "运行已取消，可继续",
                    "本次回答在完成前被停止。",
                ),
            )
            self.repo.touch_thread(thread_id)
            raise
        except Exception as exc:
            if not runtime_task.done():
                runtime_task.cancel()
            run_log.finish(
                "run_failed",
                error_type=type(exc).__name__,
                error=str(exc)[:2000],
            )
            self.repo.save_message(
                thread_id,
                "assistant",
                recovery_message(
                    "运行失败，可继续",
                    str(exc)[:500],
                ),
            )
            self.repo.touch_thread(thread_id)
            yield f"data: {json.dumps({'error': str(exc)[:500]})}\n\n"
            return
        finally:
            if not runtime_task.done():
                runtime_task.cancel()

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
        else:
            self.repo.save_message(
                thread_id,
                "assistant",
                "[运行结束但未产生输出] 模型没有返回可显示的回答。",
            )
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
