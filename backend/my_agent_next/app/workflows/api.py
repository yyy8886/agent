"""HTTP API for workflow drafts and isolated workflow runs."""

import json
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..chat_repository import ChatRepository

from .service import (
    DEFAULT_WORKFLOW_SOURCE,
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowService,
)
from .run_manager import WorkflowRunManager


def create_workflow_router(service: WorkflowService | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/workflows", tags=["workflows"])
    workflow_service = service or WorkflowService()
    run_manager = WorkflowRunManager(workflow_service.repository)

    def handle(exc: ValueError) -> HTTPException:
        if isinstance(exc, WorkflowNotFoundError):
            return HTTPException(404, str(exc))
        if isinstance(exc, WorkflowConflictError):
            return HTTPException(409, str(exc))
        return HTTPException(400, str(exc))

    @router.get("")
    def list_workflows():
        return workflow_service.list()

    @router.get("/template")
    def workflow_template():
        return {"draft_source": DEFAULT_WORKFLOW_SOURCE}

    @router.get("/visual-template")
    def visual_workflow_template():
        return {"visual_graph": workflow_service.visual_template()}

    @router.post("/compile-visual")
    def compile_visual_workflow(payload: dict):
        try:
            return workflow_service.compile_visual(payload.get("visual_graph"))
        except ValueError as exc:
            raise handle(exc)

    @router.post("/validate")
    def validate_workflow(payload: dict):
        try:
            return workflow_service.validate(payload.get("draft_source"))
        except ValueError as exc:
            raise handle(exc)

    @router.post("")
    def create_workflow(payload: dict):
        try:
            return workflow_service.create(payload)
        except ValueError as exc:
            raise handle(exc)

    @router.get("/{workflow_id}/threads")
    def list_workflow_threads(workflow_id: str):
        try:
            workflow_service.get(workflow_id)
        except ValueError as exc:
            raise handle(exc)
        return ChatRepository().list_threads(f"workflow:{workflow_id}")

    @router.post("/{workflow_id}/threads")
    def create_workflow_thread(workflow_id: str, payload: dict):
        try:
            workflow_service.get(workflow_id)
        except ValueError as exc:
            raise handle(exc)
        title = str(payload.get("title", "")).strip()
        return ChatRepository().create_thread(
            str(uuid.uuid4())[:8],
            f"workflow:{workflow_id}",
            title,
        )

    @router.post("/{workflow_id}/runs")
    def run_workflow(workflow_id: str, payload: dict):
        chat_repository = ChatRepository()
        thread_id = str(payload.get("thread_id", "")).strip()
        if not thread_id:
            raise HTTPException(400, "请先新建或选择工作流对话。")
        thread = chat_repository.get_thread(thread_id)
        if thread is None or thread.get("agent_id") != f"workflow:{workflow_id}":
            raise HTTPException(404, "工作流对话不存在。")
        try:
            active = run_manager.start(
                workflow_id,
                payload.get("input", {}),
                permission_mode=str(payload.get("permission_mode", "manual")),
                recursion_limit=payload.get("recursion_limit", 50),
                timeout_seconds=payload.get("timeout_seconds", 300),
            )
        except ValueError as exc:
            raise handle(exc)

        message = str(payload.get("input", {}).get("message", ""))
        chat_repository.save_message(thread_id, "user", message)
        chat_repository.touch_thread(thread_id)
        if not thread.get("title"):
            chat_repository.update_thread_title(thread_id, message[:40])

        async def events():
            async for event in run_manager.stream(active.run_id):
                if event.get("event") == "run_output":
                    answer = str((event.get("data") or {}).get("answer", ""))
                    if answer:
                        chat_repository.save_message(thread_id, "assistant", answer)
                        chat_repository.touch_thread(thread_id)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "X-Workflow-Run-Id": active.run_id,
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Access-Control-Expose-Headers": "X-Workflow-Run-Id",
            },
        )

    @router.post("/runs/{run_id}/cancel")
    def cancel_workflow_run(run_id: str):
        if not run_manager.cancel(run_id):
            raise HTTPException(404, "工作流运行不存在或已经结束。")
        return {"cancelled": True, "run_id": run_id}

    @router.get("/{workflow_id}")
    def get_workflow(workflow_id: str):
        try:
            return workflow_service.get(workflow_id)
        except ValueError as exc:
            raise handle(exc)

    @router.put("/{workflow_id}")
    def update_workflow(workflow_id: str, payload: dict):
        try:
            return workflow_service.update(workflow_id, payload)
        except ValueError as exc:
            raise handle(exc)

    @router.delete("/{workflow_id}")
    def delete_workflow(workflow_id: str):
        try:
            workflow_service.delete(workflow_id)
            return {"deleted": True}
        except ValueError as exc:
            raise handle(exc)

    return router
