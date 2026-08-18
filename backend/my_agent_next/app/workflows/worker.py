"""Isolated process entrypoint for direct execution of user-authored LangGraph code."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..runtime_paths import SKILLS_DIR
from types import ModuleType
from typing import Any

import yaml
from langchain_core.messages import HumanMessage, SystemMessage

from ..agent_runtime import run_agent_runtime
from ..agent_profile_repository import AgentProfileRepository
from ..chat_service import (
    ChatService,
    _build_model,
    _message_text,
    _tool_names_for_skills,
    build_agent_context_messages,
)
from ..tools import TOOL_BY_NAME
from ..tools.base import is_dangerous_command
from .contract import (
    WorkflowCancelledError,
    WorkflowContractError,
    WorkflowRunInfo,
    WorkflowRuntime,
    _bind_workflow_gateway,
    normalize_workflow_payload,
)


MAX_CHILD_DEPTH = 8
MAX_EVENT_VALUE_CHARS = 20_000
SENSITIVE_KEY_PARTS = ("api_key", "apikey", "authorization", "cookie", "password", "secret", "token")


@dataclass(frozen=True, slots=True)
class WorkerSpec:
    run_id: str
    workflow_id: str
    artifact_paths: dict[str, str]
    dependencies: dict[str, dict[str, str]]
    inputs: dict
    permission_mode: str
    recursion_limit: int
    max_agent_iterations: int = 60


class EventEmitter:
    def __init__(self, queue, root_run_id: str) -> None:
        self.queue = queue
        self.root_run_id = root_run_id
        self.sequence = 0

    def emit(self, event: str, data: object, *, run_id: str, parent_run_id: str | None = None) -> None:
        self.sequence += 1
        self.queue.put({
            "event": event,
            "run_id": run_id,
            "root_run_id": self.root_run_id,
            "parent_run_id": parent_run_id,
            "sequence": self.sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": _safe_value(data),
        })


class WorkerGateway:
    def __init__(
        self,
        spec: WorkerSpec,
        emitter: EventEmitter,
        cancel_event,
        *,
        run_id: str,
        workflow_id: str,
        parent_run_id: str | None,
        call_depth: int,
        call_stack: tuple[str, ...],
    ) -> None:
        self.spec = spec
        self.emitter = emitter
        self.cancel_event = cancel_event
        self.run_id = run_id
        self.workflow_id = workflow_id
        self.parent_run_id = parent_run_id
        self.call_depth = call_depth
        self.call_stack = call_stack

    def raise_if_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise WorkflowCancelledError("工作流已被用户停止。")

    async def call_agent(
        self,
        agent_id: str,
        inputs: dict,
        *,
        timeout_seconds: float | None = None,
        step_id: str | None = None,
        route: str | None = None,
    ) -> dict:
        self.raise_if_cancelled()
        self.emitter.emit(
            "agent_started",
            {"agent_id": agent_id, "input": inputs, "step_id": step_id, "workflow_id": self.workflow_id},
            run_id=self.run_id,
            parent_run_id=self.parent_run_id,
        )
        result = await _with_timeout(
            self._run_agent(agent_id, inputs, step_id=step_id, route=route),
            timeout_seconds,
        )
        self.emitter.emit("agent_output", {"agent_id": agent_id, "output": result}, run_id=self.run_id, parent_run_id=self.parent_run_id)
        return result

    async def _run_agent(
        self,
        agent_id: str,
        inputs: dict,
        *,
        step_id: str | None,
        route: str | None,
    ) -> dict:
        agent = AgentProfileRepository().get(agent_id)
        if agent is None or not agent.enabled:
            raise WorkflowContractError(f"Agent 不存在或未启用：{agent_id}")
        profile = ChatService.resolve_model_or_raise(agent.model_profile_id)
        user_text = str(inputs.get("message") or json.dumps(inputs, ensure_ascii=False))
        messages, selected_skill_names = build_agent_context_messages(agent, user_text)
        messages.append(SystemMessage(content=_workflow_agent_context(
            workflow_id=self.workflow_id,
            step_id=step_id,
            route=route,
            call_depth=self.call_depth,
            permission_mode=self.spec.permission_mode,
            dependency_keys=tuple(self.spec.dependencies.get(self.workflow_id, {})),
        )))
        from ..mcp_service import McpService
        mcp_tools = await McpService().tools_for_agent(agent_id)
        if mcp_tools:
            from ..chat_service import _mcp_tool_catalog
            messages.append(SystemMessage(content=_mcp_tool_catalog(mcp_tools)))
        allowed_tool_names = _tool_names_for_skills(selected_skill_names)
        model = _build_model(
            profile,
            allowed_tool_names=allowed_tool_names,
            extra_tools=list(mcp_tools.values()) if allowed_tool_names is None else [],
        )
        for skill_name in selected_skill_names:
            self.emitter.emit(
                "agent_skill_loaded",
                {"agent_id": agent_id, "skill": skill_name},
                run_id=self.run_id,
                parent_run_id=self.parent_run_id,
            )
        messages.append(HumanMessage(content=user_text))

        async def emit(event: str, data: dict) -> None:
            if event == "token":
                self.emitter.emit(
                    "agent_token",
                    {"agent_id": agent_id, "text": data.get("text", "")},
                    run_id=self.run_id,
                    parent_run_id=self.parent_run_id,
                )
            elif event == "tool_call":
                self.emitter.emit(
                    "agent_tool_call",
                    {
                        "agent_id": agent_id,
                        "tool": data.get("name", ""),
                        "arguments": data.get("args", {}),
                    },
                    run_id=self.run_id,
                    parent_run_id=self.parent_run_id,
                )
            elif event == "tool_result":
                self.emitter.emit(
                    "agent_tool_result",
                    {
                        "agent_id": agent_id,
                        "tool": data.get("name", ""),
                        "output": data.get("result", ""),
                    },
                    run_id=self.run_id,
                    parent_run_id=self.parent_run_id,
                )

        async def execute_tool(name: str, arguments: dict, call_id: str) -> str:
            if name in mcp_tools:
                from ..mcp_service import invoke_mcp_tool
                return await invoke_mcp_tool(mcp_tools[name], arguments)

            if name in {"discover_skills", "load_skill"}:
                from ..tools.skill_discovery import (
                    discover_authorized_skills,
                    load_authorized_skill,
                )

                authorized = list(agent.skills or [])
                if name == "discover_skills":
                    return discover_authorized_skills(
                        str(arguments.get("query", "")), authorized
                    )
                loaded_name = str(arguments.get("name", ""))
                output = load_authorized_skill(loaded_name, authorized)
                if output.startswith("Skill loaded:"):
                    self.emitter.emit(
                        "agent_skill_loaded",
                        {"agent_id": agent_id, "skill": loaded_name, "runtime": True},
                        run_id=self.run_id,
                        parent_run_id=self.parent_run_id,
                    )
                return output

            dangerous = name == "run_bash" and is_dangerous_command(
                str(arguments.get("command", ""))
            )
            if self.spec.permission_mode == "manual" and dangerous:
                return "工作流手动模式拒绝了危险工具调用。"
            tool = TOOL_BY_NAME.get(name)
            if tool is None:
                return f"未知工具：{name}"
            try:
                return str(await asyncio.to_thread(tool.invoke, arguments))
            except Exception as exc:
                return f"工具执行错误：{exc}"

        from ..chat_service import _is_valid_review_response

        result = await run_agent_runtime(
            messages=messages,
            model=model,
            selected_skill_names=selected_skill_names,
            max_iterations=self.spec.max_agent_iterations,
            emit=emit,
            execute_tool=execute_tool,
            message_text=_message_text,
            validate_review=_is_valid_review_response,
            check_cancelled=self.raise_if_cancelled,
        )
        return {"answer": result.answer}

    async def call_tool(self, tool_name: str, arguments: dict, *, timeout_seconds: float | None = None) -> dict:
        self.raise_if_cancelled()
        self.emitter.emit("tool_started", {"tool": tool_name, "arguments": arguments}, run_id=self.run_id, parent_run_id=self.parent_run_id)
        tool = TOOL_BY_NAME.get(tool_name)
        if tool is None:
            raise WorkflowContractError(f"未知工具：{tool_name}")
        result = await _with_timeout(asyncio.to_thread(tool.invoke, arguments), timeout_seconds)
        output = {"output": str(result)}
        self.emitter.emit("tool_output", {"tool": tool_name, "output": output}, run_id=self.run_id, parent_run_id=self.parent_run_id)
        return output

    async def call_skill(self, skill_name: str, arguments: dict, *, timeout_seconds: float | None = None) -> dict:
        self.raise_if_cancelled()
        self.emitter.emit("skill_started", {"skill": skill_name, "arguments": arguments}, run_id=self.run_id, parent_run_id=self.parent_run_id)
        output = await _with_timeout(asyncio.to_thread(_execute_skill, skill_name, arguments), timeout_seconds)
        self.emitter.emit("skill_output", {"skill": skill_name, "output": output}, run_id=self.run_id, parent_run_id=self.parent_run_id)
        return output

    async def call_mcp(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict,
        *,
        timeout_seconds: float | None = None,
    ) -> dict:
        self.raise_if_cancelled()
        self.emitter.emit(
            "mcp_started",
            {"server_id": server_id, "tool": tool_name, "arguments": arguments},
            run_id=self.run_id,
            parent_run_id=self.parent_run_id,
        )
        from ..mcp_service import McpService
        result = await _with_timeout(
            McpService().call_tool(server_id, tool_name, arguments),
            timeout_seconds,
        )
        output = {
            "text": result.get("text", ""),
            "result": result.get("result"),
            "latency_ms": result.get("latency_ms"),
        }
        self.emitter.emit(
            "mcp_output",
            {"server_id": server_id, "tool": tool_name, "output": output},
            run_id=self.run_id,
            parent_run_id=self.parent_run_id,
        )
        return output

    async def call_workflow(self, dependency_key: str, inputs: dict, *, timeout_seconds: float | None = None) -> dict:
        self.raise_if_cancelled()
        target = self.spec.dependencies.get(self.workflow_id, {}).get(dependency_key)
        if target is None:
            raise WorkflowContractError(f"未找到子工作流依赖：{dependency_key}")
        if target in self.call_stack:
            raise WorkflowContractError(f"检测到工作流循环依赖：{' -> '.join((*self.call_stack, target))}")
        if self.call_depth >= MAX_CHILD_DEPTH:
            raise WorkflowContractError(f"子工作流嵌套不能超过 {MAX_CHILD_DEPTH} 层。")
        child_run_id = str(uuid.uuid4())
        self.emitter.emit("child_workflow_started", {"dependency_key": dependency_key, "workflow_id": target, "input": inputs, "child_run_id": child_run_id}, run_id=self.run_id, parent_run_id=self.parent_run_id)
        output = await _with_timeout(
            _execute_workflow(
                self.spec, self.emitter, self.cancel_event,
                workflow_id=target, inputs=inputs, run_id=child_run_id,
                parent_run_id=self.run_id, call_depth=self.call_depth + 1,
                call_stack=(*self.call_stack, target),
            ),
            timeout_seconds,
        )
        self.emitter.emit("child_workflow_output", {"dependency_key": dependency_key, "workflow_id": target, "output": output, "child_run_id": child_run_id}, run_id=self.run_id, parent_run_id=self.parent_run_id)
        return output

    async def emit_event(self, event_type: str, data: dict) -> None:
        self.emitter.emit("custom", {"type": event_type, "data": data}, run_id=self.run_id, parent_run_id=self.parent_run_id)


async def _execute_workflow(
    spec: WorkerSpec,
    emitter: EventEmitter,
    cancel_event,
    *,
    workflow_id: str,
    inputs: dict,
    run_id: str,
    parent_run_id: str | None,
    call_depth: int,
    call_stack: tuple[str, ...],
) -> dict:
    artifact_path = spec.artifact_paths.get(workflow_id)
    if artifact_path is None:
        raise WorkflowContractError(f"缺少工作流运行产物：{workflow_id}")
    module = _load_module(workflow_id, run_id, artifact_path)
    build = getattr(module, "build_workflow", None)
    if not callable(build):
        raise WorkflowContractError("工作流没有可调用的 build_workflow()。")
    graph = build()
    if not hasattr(graph, "astream"):
        raise WorkflowContractError("build_workflow() 必须返回 compile() 后的 LangGraph。")
    normalized_inputs = normalize_workflow_payload(inputs, label="workflow input")
    if not isinstance(normalized_inputs.get("message"), str):
        raise WorkflowContractError("界面工作流输入必须包含字符串 message。")

    dependency_keys = tuple(spec.dependencies.get(workflow_id, {}))
    runtime = WorkflowRuntime(
        WorkflowRunInfo(
            run_id=run_id,
            root_run_id=spec.run_id,
            workflow_id=workflow_id,
            parent_run_id=parent_run_id,
            parent_node_id="call_workflow" if parent_run_id else None,
            call_depth=call_depth,
            permission_mode=spec.permission_mode,
        ),
        dependency_keys=dependency_keys,
    )
    gateway = WorkerGateway(
        spec, emitter, cancel_event, run_id=run_id, workflow_id=workflow_id,
        parent_run_id=parent_run_id, call_depth=call_depth, call_stack=call_stack,
    )
    emitter.emit("workflow_started", {"workflow_id": workflow_id, "input": normalized_inputs}, run_id=run_id, parent_run_id=parent_run_id)
    final_state: dict = {}
    with _bind_workflow_gateway(gateway):
        async for event in graph.astream(
            normalized_inputs,
            context=runtime,
            config={"recursion_limit": spec.recursion_limit},
            stream_mode=["tasks", "updates", "values"],
            version="v2",
        ):
            gateway.raise_if_cancelled()
            event_type = event.get("type")
            data = event.get("data")
            if event_type == "tasks":
                if "result" in data or data.get("error") is not None:
                    emitter.emit("node_finished", {"node": data.get("name"), "output": data.get("result"), "error": data.get("error")}, run_id=run_id, parent_run_id=parent_run_id)
                else:
                    emitter.emit("node_started", {"node": data.get("name"), "input": data.get("input")}, run_id=run_id, parent_run_id=parent_run_id)
            elif event_type == "updates":
                for node_name, output in data.items():
                    emitter.emit("node_output", {"node": node_name, "output": output}, run_id=run_id, parent_run_id=parent_run_id)
            elif event_type == "values" and isinstance(data, dict):
                final_state = data
    normalized_output = normalize_workflow_payload(final_state, label="workflow output")
    if not isinstance(normalized_output.get("answer"), str):
        raise WorkflowContractError("界面工作流输出必须包含字符串 answer。")
    output = {"answer": normalized_output["answer"]}
    emitter.emit("workflow_output", {"workflow_id": workflow_id, "output": output}, run_id=run_id, parent_run_id=parent_run_id)
    return output


def run_workflow_worker(spec: WorkerSpec, queue, cancel_event) -> None:
    emitter = EventEmitter(queue, spec.run_id)
    try:
        output = asyncio.run(_execute_workflow(
            spec, emitter, cancel_event, workflow_id=spec.workflow_id,
            inputs=spec.inputs, run_id=spec.run_id, parent_run_id=None,
            call_depth=0, call_stack=(spec.workflow_id,),
        ))
        emitter.emit("run_output", output, run_id=spec.run_id)
        queue.put({"event": "__complete__"})
    except WorkflowCancelledError as exc:
        emitter.emit("run_cancelled", {"message": str(exc)}, run_id=spec.run_id)
        queue.put({"event": "__complete__"})
    except BaseException as exc:
        emitter.emit("run_error", {
            "message": str(exc),
            "type": type(exc).__name__,
            "traceback": traceback.format_exc(limit=20),
            "report_id": f"workflow-{spec.run_id}",
            "run_id": spec.run_id,
            "workflow_id": spec.workflow_id,
            "worker_pid": os.getpid(),
            "fatal_base_exception": not isinstance(exc, Exception),
        }, run_id=spec.run_id)
        queue.put({"event": "__complete__"})


def _load_module(workflow_id: str, run_id: str, path: str) -> ModuleType:
    module_name = f"my_agent_next_user_workflow_{workflow_id.replace('-', '_')}_{run_id.replace('-', '_')}"
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    if module_spec is None or module_spec.loader is None:
        raise WorkflowContractError(f"无法加载工作流产物：{path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    module_spec.loader.exec_module(module)
    return module


def _execute_skill(skill_name: str, arguments: dict) -> dict:
    skill_dir = (SKILLS_DIR / skill_name).resolve()
    try:
        skill_dir.relative_to(SKILLS_DIR.resolve())
    except ValueError as exc:
        raise WorkflowContractError("Skill 路径越界。") from exc
    manifest_path = skill_dir / "execution.yaml"
    if not manifest_path.is_file():
        raise WorkflowContractError(f"Skill 不可独立执行或缺少 execution.yaml：{skill_name}")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    platform_key = "windows" if os.name == "nt" else ("macos" if sys.platform == "darwin" else "linux")
    platform = (manifest.get("platforms") or {}).get(platform_key)
    if not isinstance(platform, dict):
        raise WorkflowContractError(f"Skill 不支持当前平台：{platform_key}")
    templates = platform.get("args") or []
    values = {key: str(value) for key, value in arguments.items()}
    command = [str(platform.get("command", "")), *[str(item).format_map(_DefaultFormat(values)) for item in templates]]
    timeout = int(manifest.get("timeout_seconds", 30))
    result = subprocess.run(command, cwd=skill_dir, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        raise RuntimeError((result.stderr or output or f"Skill 退出码 {result.returncode}")[:2000])
    return {"output": output, "exit_code": result.returncode}


class _DefaultFormat(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _workflow_agent_context(
    *,
    workflow_id: str,
    step_id: str | None,
    route: str | None,
    call_depth: int,
    permission_mode: str,
    dependency_keys: tuple[str, ...],
) -> str:
    current_step = step_id or "高级代码未声明步骤 ID"
    route_text = route or "- 高级代码未提供路线摘要"
    dependencies = "、".join(dependency_keys) if dependency_keys else "无"
    return (
        "## 当前工作流运行上下文\n"
        f"- 工作流 ID：{workflow_id}\n"
        f"- 你当前所在步骤：{current_step}\n"
        f"- 子工作流调用层级：{call_depth}\n"
        f"- 权限模式：{permission_mode}\n"
        f"- 已声明子工作流依赖：{dependencies}\n"
        "- 完整路线：\n"
        f"{route_text}\n\n"
        "你只负责当前步骤。可以利用路线理解上游和下游职责，但不得声称尚未执行的"
        "节点已经完成，也不得代替其他 Agent 编造结果。当前消息中出现的上游输出才是"
        "本步骤可使用的实际结果。"
    )


async def _with_timeout(awaitable, timeout_seconds: float | None):
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds) if timeout_seconds else await awaitable


def _safe_value(value: object) -> object:
    value = _redact_value(value)
    try:
        encoded = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)[:MAX_EVENT_VALUE_CHARS]
    if len(encoded) <= MAX_EVENT_VALUE_CHARS:
        return json.loads(encoded)
    return {"truncated": True, "preview": encoded[:MAX_EVENT_VALUE_CHARS]}


def _redact_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(str(key)) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    if normalized.endswith(("_count", "_limit", "_usage")):
        return False
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
