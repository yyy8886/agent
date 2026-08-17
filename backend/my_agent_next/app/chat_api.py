# chat_api.py — 对话 API 接口层（SSE 流式）
# =============================================================================
# 本文件只负责 HTTP 请求/响应，业务逻辑交给 chat_service.py。
#
# 端点：
#   GET    /api/chat/threads?agent_id=xxx     — 列出线程
#   POST   /api/chat/threads                   — 创建线程
#   DELETE /api/chat/threads/{id}              — 删除线程
#   GET    /api/chat/threads/{id}              — 获取线程详情 + 消息列表
#   POST   /api/chat/threads/{id}/messages     — 发送消息（SSE 流式返回）
#
# 项目中的位置（三层架构）：
#   chat_api.py → chat_service.py → chat_repository.py
#   接口层        → 业务编排         → SQLite"""

import asyncio
import json
import uuid

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from .agent_profile_repository import AgentProfileRepository
from .chat_repository import ChatRepository
from .chat_service import ChatService, set_tool_decision, set_question_response
from .attachment_service import AttachmentService, MAX_ATTACHMENTS_PER_MESSAGE

router = APIRouter(prefix="/api/chat")
repo = ChatRepository()
service = ChatService(repo)
attachments = AttachmentService(prune_orphans=True)
_active_chat_tasks: dict[str, asyncio.Task] = {}

# ── 线程 ────────────────────────────────────────────────────────────────────

@router.get("/threads")
def list_threads(agent_id: str = Query(...)):
    return repo.list_threads(agent_id)


@router.post("/threads")
def create_thread(payload: dict):
    agent_id = str(payload.get("agent_id", "")).strip()
    title = str(payload.get("title", "")).strip()
    if not agent_id:
        raise HTTPException(400, "agent_id 不能为空。")
    if not AgentProfileRepository().get(agent_id):
        raise HTTPException(404, f"Agent {agent_id} 不存在。")
    return repo.create_thread(str(uuid.uuid4())[:8], agent_id, title)


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str):
    attachment_files = attachments.for_thread(thread_id)
    ok = repo.delete_thread(thread_id)
    if not ok:
        raise HTTPException(404, "线程不存在。")
    attachments.delete_files(attachment_files)
    return {"deleted": True}


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str):
    thread = repo.get_thread(thread_id)
    if not thread:
        raise HTTPException(404, "线程不存在。")
    thread["messages"] = [{
        "id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at,
        "attachments": [item.public() for item in attachments.for_message(m.id)],
    } for m in repo.get_messages(thread_id)]
    return thread


@router.post("/threads/{thread_id}/attachments")
async def upload_attachments(thread_id: str, files: list[UploadFile] = File(...)):
    if not repo.get_thread(thread_id):
        raise HTTPException(404, "线程不存在。")
    if not files or len(files) > MAX_ATTACHMENTS_PER_MESSAGE:
        raise HTTPException(400, "每次请选择 1-6 张图片。")
    saved = []
    try:
        for upload in files:
            data = await upload.read()
            saved.append(attachments.save_upload(thread_id, upload.filename or "image", data))
    except ValueError as exc:
        for item in saved:
            attachments.delete_unbound(item.id, thread_id)
        raise HTTPException(400, str(exc)) from exc
    return [item.public() for item in saved]


@router.get("/attachments/{attachment_id}/content")
def attachment_content(attachment_id: str):
    item = attachments.get(attachment_id)
    if not item:
        raise HTTPException(404, "附件不存在。")
    path = attachments.path_for(item)
    if not path.is_file():
        raise HTTPException(404, "附件文件不存在。")
    return FileResponse(path, media_type=item.mime_type)


@router.delete("/threads/{thread_id}/attachments/{attachment_id}")
def delete_attachment(thread_id: str, attachment_id: str):
    if not attachments.delete_unbound(attachment_id, thread_id):
        raise HTTPException(404, "附件不存在或已经发送。")
    return {"deleted": True}


# ── 对话（SSE 流式）─────────────────────────────────────────────────────────

@router.post("/threads/{thread_id}/messages")
async def send_message(thread_id: str, payload: dict, request: Request):
    content = str(payload.get("content", "")).strip()
    attachment_ids = payload.get("attachment_ids", [])
    if not isinstance(attachment_ids, list) or not all(isinstance(x, str) for x in attachment_ids):
        raise HTTPException(400, "attachment_ids 必须是字符串数组。")
    if not content and not attachment_ids:
        raise HTTPException(400, "消息或图片不能为空。")

    thread = repo.get_thread(thread_id)
    if not thread:
        raise HTTPException(404, "线程不存在。")

    try:
        profile = service.resolve_model_or_raise(
            AgentProfileRepository().get(thread["agent_id"]).model_profile_id
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # 读取权限模式（请求头或 payload）
    permission_mode = (
        request.headers.get("X-Permission-Mode", "")
        or str(payload.get("permission_mode", ""))
        or "manual"
    )
    max_agent_iterations = payload.get("max_agent_iterations", 60)
    if (
        not isinstance(max_agent_iterations, int)
        or isinstance(max_agent_iterations, bool)
        or not 1 <= max_agent_iterations <= 200
    ):
        raise HTTPException(400, "max_agent_iterations 必须在 1-200 之间。")

    async def cancellable_stream():
        task = asyncio.current_task()
        if task is not None:
            previous = _active_chat_tasks.get(thread_id)
            if previous is not None and previous is not task and not previous.done():
                yield f"data: {json.dumps({'error': '该对话正在生成回答，请等待完成或先点击停止。'}, ensure_ascii=False)}\n\n"
                return
            _active_chat_tasks[thread_id] = task
        try:
            async for chunk in service.stream_chat(
                thread["agent_id"], thread_id, content, profile,
                permission_mode=permission_mode,
                max_agent_iterations=max_agent_iterations,
                attachment_ids=attachment_ids,
            ):
                yield chunk
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'event': 'cancelled', 'data': {'message': 'Agent 对话已停止。'}}, ensure_ascii=False)}\n\n"
        finally:
            if _active_chat_tasks.get(thread_id) is task:
                _active_chat_tasks.pop(thread_id, None)

    return StreamingResponse(
        cancellable_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.post("/threads/{thread_id}/cancel")
async def cancel_chat(thread_id: str):
    task = _active_chat_tasks.get(thread_id)
    if task is None or task.done():
        raise HTTPException(404, "该对话当前没有正在生成的回答。")
    task.cancel()
    return {"cancelled": True}


@router.post("/threads/{thread_id}/tool-response")
def tool_response(thread_id: str, payload: dict):
    """手动模式下，用户对工具调用确认的响应。"""
    confirm_id = str(payload.get("confirm_id", "")).strip()
    allowed = bool(payload.get("allowed", False))
    if not confirm_id:
        raise HTTPException(400, "confirm_id 不能为空。")
    set_tool_decision(thread_id, confirm_id, allowed)
    return {"status": "ok"}


@router.post("/threads/{thread_id}/question-response")
def question_response(thread_id: str, payload: dict):
    """用户对 ask_user_question 的答案。"""
    call_id = str(payload.get("call_id", "")).strip()
    answers = payload.get("answers", [])
    if not call_id:
        raise HTTPException(400, "call_id 不能为空。")
    set_question_response(thread_id, call_id, answers)
    return {"status": "ok"}
