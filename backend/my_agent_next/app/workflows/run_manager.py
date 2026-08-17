"""Parent-process lifecycle management for isolated workflow workers."""

from __future__ import annotations

import asyncio
import multiprocessing
import platform
import queue as queue_module
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from .artifact import WorkflowArtifactStore
from .repository import WorkflowRepository
from .worker import WorkerSpec, run_workflow_worker


MIN_RECURSION_LIMIT = 2
MAX_RECURSION_LIMIT = 500
DEFAULT_RECURSION_LIMIT = 50
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 1800
DEFAULT_TIMEOUT_SECONDS = 300
MIN_AGENT_ITERATIONS = 1
MAX_AGENT_ITERATIONS = 200
DEFAULT_AGENT_ITERATIONS = 60
HARD_CANCEL_GRACE_SECONDS = 1.5
EXIT_QUEUE_GRACE_SECONDS = 0.25


@dataclass(slots=True)
class ActiveWorkflowRun:
    run_id: str
    workflow_id: str
    process: multiprocessing.Process
    queue: object
    cancel_event: object
    started_at: float
    timeout_seconds: int
    cancel_requested_at: float | None = None


class WorkflowRunManager:
    def __init__(
        self,
        repository: WorkflowRepository | None = None,
        artifact_store: WorkflowArtifactStore | None = None,
    ) -> None:
        self.repository = repository or WorkflowRepository()
        self.artifact_store = artifact_store or WorkflowArtifactStore()
        self._runs: dict[str, ActiveWorkflowRun] = {}
        self._lock = threading.Lock()
        self._context = multiprocessing.get_context("spawn")

    def start(
        self,
        workflow_id: str,
        inputs: object,
        *,
        permission_mode: str = "manual",
        recursion_limit: int = DEFAULT_RECURSION_LIMIT,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_agent_iterations: int = DEFAULT_AGENT_ITERATIONS,
    ) -> ActiveWorkflowRun:
        if not isinstance(inputs, dict) or not isinstance(inputs.get("message"), str) or not inputs["message"].strip():
            raise ValueError("工作流输入必须包含非空字符串 message。")
        if permission_mode not in {"manual", "plan", "auto"}:
            raise ValueError("permission_mode 必须是 manual、plan 或 auto。")
        if not isinstance(recursion_limit, int) or isinstance(recursion_limit, bool) or not MIN_RECURSION_LIMIT <= recursion_limit <= MAX_RECURSION_LIMIT:
            raise ValueError(f"recursion_limit 必须在 {MIN_RECURSION_LIMIT}-{MAX_RECURSION_LIMIT} 之间。")
        if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or not MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError(f"timeout_seconds 必须在 {MIN_TIMEOUT_SECONDS}-{MAX_TIMEOUT_SECONDS} 秒之间。")
        if not isinstance(max_agent_iterations, int) or isinstance(max_agent_iterations, bool) or not MIN_AGENT_ITERATIONS <= max_agent_iterations <= MAX_AGENT_ITERATIONS:
            raise ValueError(
                f"max_agent_iterations 必须在 {MIN_AGENT_ITERATIONS}-{MAX_AGENT_ITERATIONS} 之间。"
            )

        artifacts: dict[str, str] = {}
        dependencies: dict[str, dict[str, str]] = {}
        self._snapshot(workflow_id, artifacts, dependencies, stack=())
        run_id = str(uuid.uuid4())
        event_queue = self._context.Queue()
        cancel_event = self._context.Event()
        spec = WorkerSpec(
            run_id=run_id,
            workflow_id=workflow_id,
            artifact_paths=artifacts,
            dependencies=dependencies,
            inputs={"message": inputs["message"]},
            permission_mode=permission_mode,
            recursion_limit=recursion_limit,
            max_agent_iterations=max_agent_iterations,
        )
        process = self._context.Process(
            target=run_workflow_worker,
            args=(spec, event_queue, cancel_event),
            name=f"workflow-{workflow_id}-{run_id[:8]}",
            daemon=True,
        )
        process.start()
        active = ActiveWorkflowRun(
            run_id, workflow_id, process, event_queue, cancel_event,
            time.monotonic(), timeout_seconds,
        )
        with self._lock:
            self._runs[run_id] = active
        return active

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            active = self._runs.get(run_id)
            if active is None:
                return False
            active.cancel_event.set()
            active.cancel_requested_at = active.cancel_requested_at or time.monotonic()
            return True

    async def stream(self, run_id: str) -> AsyncIterator[dict]:
        with self._lock:
            active = self._runs.get(run_id)
        if active is None:
            raise ValueError("工作流运行不存在。")
        completed = False
        checkpoints: deque[dict] = deque(maxlen=8)

        def remember(event: dict) -> None:
            data = event.get("data") or {}
            checkpoint = {
                "event": event.get("event"),
                "sequence": event.get("sequence"),
                "timestamp": event.get("timestamp"),
            }
            for key in ("node", "agent_id", "tool", "skill", "workflow_id"):
                if key in data:
                    checkpoint[key] = str(data[key])[:160]
            checkpoints.append(checkpoint)

        def unexpected_exit(exit_code: int | None) -> dict:
            return {
                "message": f"Worker 意外退出，退出码 {exit_code}。",
                "type": "WorkerUnexpectedExit",
                "report_id": f"workflow-{run_id}",
                "run_id": run_id,
                "workflow_id": active.workflow_id,
                "worker_pid": active.process.pid,
                "exit_code": exit_code,
                "exit_code_hint": (
                    "退出码 1 通常表示子进程中存在未捕获异常、解释器启动失败，"
                    "或开发服务器热重载终止了 Worker。"
                    if exit_code == 1
                    else "负退出码通常表示进程被信号或外部机制终止。"
                    if isinstance(exit_code, int) and exit_code < 0
                    else "该退出码没有更具体的平台解释。"
                ),
                "elapsed_seconds": round(time.monotonic() - active.started_at, 3),
                "timeout_seconds": active.timeout_seconds,
                "cancel_requested": active.cancel_requested_at is not None,
                "last_checkpoints": list(checkpoints),
                "python": sys.version,
                "platform": platform.platform(),
                "next_step": "请提供此 data 对象及对应工作流运行轨迹。",
            }
        try:
            while True:
                now = time.monotonic()
                if now - active.started_at > active.timeout_seconds and active.cancel_requested_at is None:
                    active.cancel_event.set()
                    active.cancel_requested_at = now
                    yield {"event": "run_timeout", "run_id": run_id, "data": {"timeout_seconds": active.timeout_seconds}}
                if active.cancel_requested_at is not None and now - active.cancel_requested_at > HARD_CANCEL_GRACE_SECONDS and active.process.is_alive():
                    active.process.terminate()
                    active.process.join(timeout=1)
                    yield {"event": "run_cancelled", "run_id": run_id, "data": {"message": "Worker 已被强制终止。"}}
                    completed = True
                    break
                drained = False
                while True:
                    try:
                        event = active.queue.get_nowait()
                    except queue_module.Empty:
                        break
                    drained = True
                    if event.get("event") == "__complete__":
                        completed = True
                        break
                    remember(event)
                    yield event
                if completed:
                    break
                if not active.process.is_alive():
                    deadline = time.monotonic() + EXIT_QUEUE_GRACE_SECONDS
                    while time.monotonic() < deadline:
                        try:
                            event = active.queue.get(timeout=0.04)
                        except queue_module.Empty:
                            continue
                        if event.get("event") == "__complete__":
                            completed = True
                            break
                        remember(event)
                        yield event
                    if completed:
                        break
                    exit_code = active.process.exitcode
                    yield {
                        "event": "run_error",
                        "run_id": run_id,
                        "data": unexpected_exit(exit_code),
                    }
                    break
                await asyncio.sleep(0.04 if drained else 0.08)
        finally:
            if active.process.is_alive():
                active.cancel_event.set()
                active.process.join(timeout=HARD_CANCEL_GRACE_SECONDS)
            if active.process.is_alive():
                active.process.terminate()
                active.process.join(timeout=1)
            try:
                active.queue.close()
                active.queue.join_thread()
            except Exception:
                pass
            with self._lock:
                self._runs.pop(run_id, None)

    def _snapshot(
        self,
        workflow_id: str,
        artifacts: dict[str, str],
        dependencies: dict[str, dict[str, str]],
        *,
        stack: tuple[str, ...],
    ) -> None:
        if workflow_id in stack:
            raise ValueError(f"检测到工作流循环依赖：{' -> '.join((*stack, workflow_id))}")
        if workflow_id in artifacts:
            return
        draft = self.repository.get(workflow_id)
        if draft is None:
            raise ValueError(f"工作流不存在：{workflow_id}")
        artifact = self.artifact_store.materialize(draft)
        artifacts[workflow_id] = str(artifact.path)
        dependencies[workflow_id] = {item.key: item.target_workflow_id for item in draft.dependencies}
        for item in draft.dependencies:
            self._snapshot(item.target_workflow_id, artifacts, dependencies, stack=(*stack, workflow_id))
