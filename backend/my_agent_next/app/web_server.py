# web_server.py — FastAPI 接口层 + Web 管理页面
# =============================================================================
# 本文件是项目的"对外接口层"，提供 REST API 和 Web 管理页面。
#
# 接口列表：
#   GET  /                      → 返回管理页面（static/index.html）
#   GET  /api/profiles          → 列出所有 API 配置
#   POST /api/profiles          → 新增/更新配置
#   DELETE /api/profiles/{id}   → 删除配置（不可删默认配置）
#   POST /api/profiles/{id}/set-default → 设为默认
#   POST /api/profiles/{id}/speed-test  → 测速：发一个 "Hi"，返回延迟 ms
#   GET  /api/agents            → 列出所有 Agent
#   POST /api/agents            → 新增/更新 Agent
#   DELETE /api/agents/{id}     → 删除 Agent
#   GET  /api/skills            → 列出所有可用 Skill
#   GET  /api/model-options     → 列出可选的 API Profile（供 Agent 绑定模型用）
#
# 启动方式：
#   python -m my_agent_next.app.web_server
#   端口等设置见 my_agent_next/config.yaml
#
# 项目中的位置（三层架构）：
#   web_server.py (接口层) → ApiProfileService (业务层) → ApiProfileRepository (数据层)
#   浏览器/HTTP             → 用例逻辑                → SQLite"""

import os
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api_profile_service import ApiProfileService
from .agent_profile_service import AgentProfileService
from .chat_api import router as chat_router
from .marketplace_api import router as marketplace_router

# 项目根目录 = my_agent_next/
project_dir = Path(__file__).resolve().parent.parent

# 加载 my_agent_next/.env（API Key 在这里配置）
load_dotenv(project_dir / ".env")

# 加载 my_agent_next/config.yaml（端口等设置在这里配置）
with open(project_dir / "config.yaml", "r", encoding="utf-8") as f:
    _config = yaml.safe_load(f)

app = FastAPI(title="My Agent Next — 管理中心")
service = ApiProfileService()
agent_service = AgentProfileService()

# ── 静态文件（前端页面）──────────────────────────────────────────────────────
static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    """返回管理页面。"""
    return (static_dir / "index.html").read_text(encoding="utf-8")


# ── REST API ─────────────────────────────────────────────────────────────────


@app.get("/api/profiles")
def list_profiles():
    """列出所有 API 配置。"""
    return service.list()


@app.post("/api/profiles")
def save_profile(payload: dict):
    """新增或更新一个 API 配置。"""
    try:
        return service.save(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: str):
    """删除一个 API 配置（不能删除默认配置）。"""
    try:
        ok = service.delete(profile_id)
        if not ok:
            raise HTTPException(status_code=404, detail="配置不存在。")
        return {"deleted": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/profiles/{profile_id}/set-default")
def set_default(profile_id: str):
    """设为默认配置。"""
    try:
        return service.set_default(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── 挂载对话路由 ────────────────────────────────────────────────────────────
app.include_router(chat_router)
app.include_router(marketplace_router)

# ── Agent 管理 ──────────────────────────────────────────────────────────────


@app.get("/api/agents")
def list_agents():
    """列出所有 Agent 配置。"""
    return agent_service.list()


@app.post("/api/agents")
def save_agent(payload: dict):
    """新增或更新一个 Agent 配置。"""
    try:
        return agent_service.save(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: str):
    """删除一个 Agent 配置。"""
    ok = agent_service.delete(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Agent 不存在。")
    return {"deleted": True}


@app.get("/api/skills")
def list_skills():
    """返回所有可用的 Skill 列表。"""
    return agent_service.available_skills()


@app.get("/api/model-options")
def list_model_options():
    """返回可选的 API Profile 列表（供 Agent 绑定模型）。"""
    return agent_service.model_options()


# ── 测速 ─────────────────────────────────────────────────────────────────────


@app.post("/api/profiles/{profile_id}/speed-test")
def speed_test(profile_id: str):
    """对指定配置发起一次简短调用，返回耗时与是否成功。"""
    profile = service.repository.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="配置不存在。")

    # Ollama 不需要 Key；远程 provider 需要检查环境变量
    if profile.provider != "ollama":
        key = os.getenv(profile.api_key_env or "")
        if not key:
            raise HTTPException(
                status_code=400,
                detail=f"未找到环境变量 {profile.api_key_env}，无法测速。",
            )

    try:
        model = _build_model(profile)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"创建模型失败：{exc}")

    prompt = "Hi"  # 最短提示词，减少 token 消耗
    start = time.perf_counter()
    try:
        response = model.invoke(prompt)
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        return {
            "profile_id": profile_id,
            "provider": profile.provider,
            "model": profile.model,
            "latency_ms": elapsed_ms,
            "success": True,
            "response_preview": response.content[:200] if hasattr(response, "content") else str(response)[:200],
        }
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        return {
            "profile_id": profile_id,
            "provider": profile.provider,
            "model": profile.model,
            "latency_ms": elapsed_ms,
            "success": False,
            "error": str(exc)[:500],
        }


def _build_model(profile):
    """根据 ApiProfile 创建对应的 LangChain ChatModel。"""
    common = {
        "model": profile.model,
        "temperature": profile.temperature,
    }

    if profile.provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(
            **common,
            api_key=os.getenv(profile.api_key_env or ""),
            base_url=profile.base_url or "https://api.deepseek.com",
            timeout=profile.timeout_seconds,
            max_retries=profile.max_retries,
        )
    elif profile.provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            **common,
            api_key=os.getenv(profile.api_key_env or ""),
            base_url=profile.base_url or "https://api.openai.com/v1",
            timeout=profile.timeout_seconds,
            max_retries=profile.max_retries,
        )
    elif profile.provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            **common,
            base_url=profile.base_url or "http://127.0.0.1:11434",
        )
    else:
        raise ValueError(f"不支持的 provider：{profile.provider}")


# ── 启动入口 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    import webbrowser

    host = _config.get("server", {}).get("host", "127.0.0.1")
    port = _config.get("server", {}).get("port", 9800)
    auto_open = _config.get("server", {}).get("auto_open_browser", True)
    url = f"http://{host}:{port}"

    if auto_open:
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run("my_agent_next.app.web_server:app", host=host, port=port, reload=True)
