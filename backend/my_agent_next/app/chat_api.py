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

import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from .agent_profile_repository import AgentProfileRepository
from .chat_repository import ChatRepository
from .chat_service import ChatService, set_tool_decision, set_question_response

router = APIRouter(prefix="/api/chat")
repo = ChatRepository()
service = ChatService(repo)

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
    ok = repo.delete_thread(thread_id)
    if not ok:
        raise HTTPException(404, "线程不存在。")
    return {"deleted": True}


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str):
    thread = repo.get_thread(thread_id)
    if not thread:
        raise HTTPException(404, "线程不存在。")
    thread["messages"] = [{
        "id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at
    } for m in repo.get_messages(thread_id)]
    return thread


# ── 对话（SSE 流式）─────────────────────────────────────────────────────────

@router.post("/threads/{thread_id}/messages")
async def send_message(thread_id: str, payload: dict, request: Request):
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(400, "消息不能为空。")

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

    return StreamingResponse(
        service.stream_chat(thread["agent_id"], thread_id, content, profile,
                           permission_mode=permission_mode),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


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
