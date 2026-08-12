# marketplace_api.py — Skill 市场 API
# =============================================================================
# 搜索 SkillsMP 和 ClawHub，下载并通过 AI 解析层适配为标准 SKILL.md 格式，
# 最后安装到本地 skills/ 目录。
#
# 端点：
#   GET  /api/marketplace/search?q=&source=all&page=1
#   GET  /api/marketplace/skill/{source}/{slug}
#   POST /api/marketplace/install
#
# AI 解析层：
#   安装时自动调用默认模型，将任意格式的 Skill 内容转换为标准 SKILL.md
#   （YAML frontmatter + markdown body），并映射工具引用到我们支持的 8 个工具。
#   如果 AI 调用失败，降级为直接保存原始内容。
# =============================================================================

import json
import os
import re
import zipfile
import io
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/marketplace")

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
SKILLS_DIR.mkdir(exist_ok=True)

CLAWHUB_BASE = "https://clawhub.ai/api/v1"
SKILLSMP_BASE = "https://skillsmp.com/api/v1"

# HTTP 客户端
_client = httpx.Client(timeout=15.0)

# AI 适配用的 prompt 模板
_AI_ADAPT_SYSTEM_PROMPT = """你是一个 Skill 格式标准化工具。你的任务是将任意格式的 Skill/AI 插件描述转换为标准 SKILL.md 格式。

## 标准 SKILL.md 格式

```
---
name: <skill-name>
description: <一句话描述这个 Skill 做什么>
---

# <Skill 标题>

## 功能
- 功能点 1
- 功能点 2

## 使用方式
描述什么时候应该使用这个 Skill，以及如何触发。

## 可用工具
本平台提供以下工具，请在 Skill 指令中只引用这些工具：

| 工具名 | 签名 | 用途 |
|--------|------|------|
| read_file | (path, offset?, limit?) | 读取文件内容 |
| write_file | (path, content) | 写入/覆盖文件 |
| edit_file | (path, old_string, new_string) | 精确字符串替换 |
| glob | (pattern, path?) | 文件模式匹配查找 |
| grep | (pattern, path?) | 搜索文件内容（正则） |
| run_bash | (command, timeout?) | 执行 Shell 命令 |
| web_fetch | (url) | 获取网页内容 |
| web_search | (query, max_results?) | 搜索互联网 |

## 要求

1. 从输入内容中提取核心指令、工作流、规则，用中文重新组织
2. 确保 YAML frontmatter 包含 name 和 description
3. 如果原文引用了不存在的工具，映射到上面最接近的工具
4. 如果原文是给其他平台写的（Codex/OpenClaw/Cursor），去除平台特定指令，保留通用逻辑
5. 保持简洁——Skill 是给另一个 AI 看的操作手册，不是给用户看的文档
6. 正文不要超过 200 行

只输出 SKILL.md 内容，不要加任何解释。"""


def _ai_adapt_skill(raw_content: str, name: str, description: str) -> str:
    """使用默认模型将原始 Skill 内容转换为标准 SKILL.md 格式。

    如果 AI 调用失败，返回 None（调用方降级为保存原始内容）。
    """
    from .chat_service import ChatService

    try:
        profile = ChatService.resolve_model(None)
        if not profile:
            print("[marketplace] AI 适配跳过：没有可用的默认模型")
            return None
    except Exception as exc:
        print(f"[marketplace] AI 适配跳过：获取模型失败 - {exc}")
        return None

    user_prompt = f"""请将以下 Skill 内容转换为标准 SKILL.md 格式。

原始名称: {name}
原始描述: {description}

---原始内容开始---
{raw_content[:8000]}
---原始内容结束---"""

    try:
        model = _build_adapt_model(profile)
        response = model.invoke([
            {"role": "system", "content": _AI_ADAPT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])
        adapted = response.content if hasattr(response, "content") else str(response)

        # 验证输出包含 frontmatter
        if not adapted.strip().startswith("---"):
            print("[marketplace] AI 适配警告：输出缺少 frontmatter，包一层")
            adapted = f"---\nname: {name}\ndescription: {description}\n---\n\n{adapted}"

        print(f"[marketplace] AI 适配成功：{len(raw_content)} → {len(adapted)} 字符")
        return adapted
    except Exception as exc:
        print(f"[marketplace] AI 适配失败（降级为原始内容）: {exc}")
        return None


def _build_adapt_model(profile):
    """构建用于 AI 适配的模型（不带工具绑定，只需要文本生成）。"""
    common = {"model": profile.model, "temperature": 0.3}
    if profile.provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(**common, api_key=os.getenv(profile.api_key_env or ""),
                           base_url=profile.base_url or "https://api.deepseek.com",
                           timeout=profile.timeout_seconds,
                           max_retries=profile.max_retries)
    elif profile.provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(**common, api_key=os.getenv(profile.api_key_env or ""),
                         base_url=profile.base_url or "https://api.openai.com/v1",
                         timeout=profile.timeout_seconds,
                         max_retries=profile.max_retries)
    elif profile.provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(**common,
                         base_url=profile.base_url or "http://127.0.0.1:11434")
    raise ValueError(f"不支持的 provider：{profile.provider}")


# ── 搜索 ────────────────────────────────────────────────────────────────────


@router.get("/search")
def search_marketplace(
    q: str = Query(default=""),
    source: str = Query(default="all"),
    page: int = Query(default=1, ge=1, le=20),
    sort: str = Query(default="trending"),
):
    """搜索 Skill 市场（ClawHub + SkillsMP）。"""
    results = []

    if source in ("all", "clawhub"):
        try:
            clawhub_results = _search_clawhub(q, page, sort)
            results.extend(clawhub_results)
        except Exception as exc:
            print(f"[marketplace] ClawHub 搜索失败: {exc}")

    if source in ("all", "skillsmp"):
        try:
            skillsmp_results = _search_skillsmp(q, page)
            results.extend(skillsmp_results)
        except Exception as exc:
            print(f"[marketplace] SkillsMP 搜索失败: {exc}")

    # 标记已安装状态
    installed = _installed_skill_names()
    for item in results:
        item["installed"] = item.get("name", "") in installed

    # 客户端排序：trending 按下载量降序，relevance 保持原始顺序
    if sort == "trending":
        results.sort(key=lambda x: x.get("downloads", 0), reverse=True)

    return {"items": results, "total": len(results), "page": page, "q": q, "sort": sort}


def _search_clawhub(q: str, page: int, sort: str) -> list[dict]:
    """搜索 ClawHub。"""
    try:
        resp = _client.get(
            f"{CLAWHUB_BASE}/search",
            params={"q": q, "limit": 20, "sort": sort},
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = data.get("skills", data.get("results", data.get("items", [])))
        return [
            {
                "name": item.get("slug", item.get("name", "")),
                "description": (item.get("summary") or item.get("description") or "")[:200],
                "source": "clawhub",
                "slug": item.get("slug", ""),
                "version": "",
                "downloads": item.get("downloads", item.get("stars", 0)),
                "author": _extract_author(item.get("publisher", item.get("owner", ""))),
            }
            for item in items
        ][:20]
    except Exception:
        return []


def _search_skillsmp(q: str, page: int) -> list[dict]:
    """搜索 SkillsMP。"""
    try:
        resp = _client.get(
            f"{SKILLSMP_BASE}/skills/search",
            params={"q": q, "page": page, "limit": 20},
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        # SkillsMP 返回格式: {success: true, data: {skills: [...]}}
        items = data.get("data", {}).get("skills", [])
        if not items:
            items = data.get("skills", data.get("results", data.get("items", [])))
        return [
            {
                "name": item.get("name", item.get("slug", "")),
                "description": (item.get("description") or "")[:200],
                "source": "skillsmp",
                "slug": item.get("id", item.get("name", "")),
                "version": "",
                "downloads": item.get("stars", item.get("downloads", 0)),
                "author": item.get("author", item.get("owner", "")),
                "github_url": item.get("githubUrl", ""),
                "skill_url": item.get("skillUrl", ""),
            }
            for item in items
        ][:20]
    except Exception:
        return []


# ── 获取 Skill 详情 ────────────────────────────────────────────────────────


@router.get("/skill/{source}/{slug}")
def get_skill_detail(source: str, slug: str, url: str = Query(default="")):
    """获取 Skill 的 SKILL.md 内容（安装前预览）。可传入 github_url 直接从 GitHub 获取。"""
    if source == "clawhub":
        return _get_clawhub_skill(slug)
    elif source == "skillsmp":
        return _get_skillsmp_skill(slug, github_url=url)
    raise HTTPException(400, f"不支持的来源：{source}")


def _get_clawhub_skill(slug: str) -> dict:
    """获取 ClawHub Skill 详情。"""
    try:
        resp = _client.get(f"{CLAWHUB_BASE}/skills/{slug}")
        if resp.status_code != 200:
            raise HTTPException(404, f"ClawHub 未找到：{slug}")
        data = resp.json()
        # ClawHub 返回格式可能是 {skill: {...}} 或直接就是 skill 对象
        skill_data = data.get("skill", data)
        # ClawHub skill 详情：skill.description 是完整 SKILL.md，skill.summary 是简介
        description = (skill_data.get("summary") or skill_data.get("description") or "")
        # content 优先取 description（它可能就是 SKILL.md），再取 readme/content
        content = (skill_data.get("description") or skill_data.get("readme")
                   or skill_data.get("content") or "")
        return {
            "name": skill_data.get("slug", slug),
            "description": description[:200] if len(description) > 200 else description,
            "source": "clawhub",
            "slug": slug,
            "version": "",
            "files": skill_data.get("files", []),
            "content": content,
        }
    except httpx.HTTPError:
        raise HTTPException(502, "ClawHub 请求失败")


def _get_skillsmp_skill(slug: str, github_url: str = "") -> dict:
    """获取 SkillsMP Skill 详情。

    SkillsMP 没有单独获取 Skill 的 API。
    优先用传入的 github_url 直接从 GitHub 获取，否则用 slug 搜索。
    """
    skill_url = ""
    description = ""
    name = slug

    # 1. 如果有 github_url，直接尝试从 GitHub 获取内容
    if github_url:
        content = _fetch_github_skill(github_url)
        if content:
            return {
                "name": name,
                "description": description,
                "source": "skillsmp",
                "slug": slug,
                "version": "",
                "files": [],
                "content": content,
            }

    # 2. 用 slug 搜索找到元信息和 githubUrl
    try:
        search_resp = _client.get(
            f"{SKILLSMP_BASE}/skills/search",
            params={"q": slug.replace("-", " "), "limit": 20},
        )
        if search_resp.status_code == 200:
            search_data = search_resp.json()
            skills = search_data.get("data", {}).get("skills", [])
            for sk in skills:
                if sk.get("id") == slug or sk.get("name") == slug:
                    github_url = sk.get("githubUrl", "")
                    skill_url = sk.get("skillUrl", "")
                    name = sk.get("name", slug)
                    description = sk.get("description", "")
                    # 尝试从 GitHub URL 获取内容
                    if github_url:
                        content = _fetch_github_skill(github_url)
                        if content:
                            return {
                                "name": name, "description": description,
                                "source": "skillsmp", "slug": slug,
                                "version": "", "files": [], "content": content,
                            }
                    # GitHub 获取失败，返回元信息
                    return {
                        "name": name, "description": description,
                        "source": "skillsmp", "slug": slug,
                        "version": "", "files": [],
                        "content": f"# {name}\n\n{description}\n\nSkill URL: {skill_url}\nGitHub: {github_url}",
                    }
    except Exception:
        pass

    raise HTTPException(404, f"SkillsMP 未找到：{slug}")


# ── 安装 Skill ─────────────────────────────────────────────────────────────


@router.post("/install")
def install_skill(payload: dict):
    """从市场下载并通过 AI 解析层适配后安装到本地 skills/ 目录。

    流程：下载原始内容 → AI 标准化为 SKILL.md → 保存到 skills/<name>/
    如果 AI 适配失败，降级为直接保存原始内容。
    """
    source = str(payload.get("source", ""))
    slug = str(payload.get("slug", ""))
    github_url = str(payload.get("github_url", ""))

    if not source or not slug:
        raise HTTPException(400, "source 和 slug 不能为空")

    # 1. 下载原始内容
    detail = get_skill_detail(source, slug, url=github_url)
    content = detail.get("content", "")
    name = detail.get("name", slug)
    description = detail.get("description", "")

    if not content:
        # 尝试下载 ZIP
        if source == "clawhub":
            content = _download_clawhub_skill(slug, name)
        if not content:
            raise HTTPException(400, "无法获取 Skill 内容")

    # 2. AI 适配：将任意格式转换为标准 SKILL.md
    adapted = _ai_adapt_skill(content, name, description)

    if adapted:
        content = adapted
        ai_adapted = True
    else:
        # 降级：简单包装 frontmatter
        if not content.strip().startswith("---"):
            content = f"---\nname: {name}\ndescription: {description}\n---\n\n{content}"
        ai_adapted = False

    # 3. 保存到 skills/<name>/SKILL.md
    skill_dir = SKILLS_DIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    return {
        "installed": True,
        "name": name,
        "path": str(skill_dir.relative_to(SKILLS_DIR.parent)),
        "source": source,
        "ai_adapted": ai_adapted,
    }


def _download_clawhub_skill(slug: str, name: str) -> str:
    """从 ClawHub 下载 Skill ZIP 并提取 SKILL.md。"""
    try:
        resp = _client.get(f"{CLAWHUB_BASE}/download", params={"slug": slug})
        if resp.status_code != 200:
            return ""
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for info in zf.filelist:
                if info.filename.endswith("SKILL.md") or info.filename.endswith("README.md"):
                    return zf.read(info.filename).decode("utf-8", errors="replace")
            # 没有 markdown 文件，列出所有文件
            files = [f.filename for f in zf.filelist[:10]]
            return f"ZIP 内容：{', '.join(files)}"
    except Exception as exc:
        print(f"[marketplace] 下载 ClawHub Skill 失败: {exc}")
        return ""


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _fetch_github_skill(github_url: str) -> str:
    """从 GitHub URL 获取 SKILL.md 内容。

    处理两种 URL 格式：
    - https://github.com/owner/repo/tree/main/path → raw URL
    - https://github.com/owner/repo/blob/main/path → raw URL
    """
    if not github_url:
        return ""

    # 尝试从 GitHub URL 推导 raw URL
    raw_url = github_url.replace("github.com", "raw.githubusercontent.com")
    raw_url = raw_url.replace("/tree/", "/").replace("/blob/", "/")

    # 尝试获取 SKILL.md
    for filename in ["SKILL.md", "README.md", "readme.md"]:
        try:
            url = f"{raw_url.rstrip('/')}/{filename}"
            resp = _client.get(url)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            continue

    # 如果 raw URL 失败，尝试 GitHub API
    # https://api.github.com/repos/owner/repo/contents/path
    try:
        import re
        match = re.match(r"https?://github\.com/([^/]+)/([^/]+)(?:/tree|/blob)?/(.+?)(?:/SKILL\.md)?$", github_url)
        if match:
            owner, repo, path = match.groups()
            path = path.rstrip("/")
            api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
            resp = _client.get(api_url, headers={"Accept": "application/vnd.github.v3+json"})
            if resp.status_code == 200:
                items = resp.json()
                if isinstance(items, list):
                    # 目录：找 SKILL.md 或 README.md
                    for item in items:
                        if item.get("name") in ("SKILL.md", "README.md"):
                            if item.get("download_url"):
                                raw_resp = _client.get(item["download_url"])
                                if raw_resp.status_code == 200:
                                    return raw_resp.text
                elif isinstance(items, dict):
                    # 文件
                    if items.get("download_url"):
                        raw_resp = _client.get(items["download_url"])
                        if raw_resp.status_code == 200:
                            return raw_resp.text
    except Exception:
        pass

    return ""


def _extract_author(author_raw) -> str:
    """从 ClawHub 的作者字段提取可读名称。ClawHub 返回的 author 可能是对象。"""
    if isinstance(author_raw, dict):
        return author_raw.get("displayName", author_raw.get("handle", ""))
    if isinstance(author_raw, str):
        return author_raw
    return ""


def _installed_skill_names() -> set[str]:
    """返回已安装的 Skill 名称集合。"""
    names = set()
    for entry in SKILLS_DIR.iterdir():
        if entry.is_dir() and not entry.name.startswith("_") and not entry.name.startswith("."):
            if (entry / "SKILL.md").exists():
                names.add(entry.name)
    return names
