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
                "owner_handle": item.get("ownerHandle", ""),
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


@router.get("/skill/local/{name}")
def get_local_skill(name: str):
    """读取本地已安装 Skill 的 SKILL.md 内容。"""
    skill_dir = SKILLS_DIR / name
    md_file = skill_dir / "SKILL.md"
    if not md_file.is_file():
        raise HTTPException(404, f"本地 Skill「{name}」不存在")
    content = md_file.read_text(encoding="utf-8")
    return {"name": name, "content": content, "source": "local"}


@router.get("/skill/{source}/{slug}")
def get_skill_detail(source: str, slug: str, url: str = Query(default=""), owner: str = Query(default="")):
    """获取 Skill 的 SKILL.md 内容（安装前预览）。可传入 github_url 或 owner_handle。"""
    if source == "clawhub":
        return _get_clawhub_skill(slug, owner_handle=owner)
    elif source == "skillsmp":
        return _get_skillsmp_skill(slug, github_url=url)
    raise HTTPException(400, f"不支持的来源：{source}")


def _get_clawhub_skill(slug: str, owner_handle: str = "") -> dict:
    """获取 ClawHub Skill 详情。

    ClawHub v1 详情接口使用裸 slug。owner_handle 仅用于在 409
    同名冲突响应中选择正确作者，不能拼进详情 URL。
    """
    try:
        resp = _client.get(f"{CLAWHUB_BASE}/skills/{slug}")

        # 409 冲突：有多个同名 Skill
        if resp.status_code == 409:
            data = resp.json()
            matches = data.get("matches", [])
            if matches:
                selected = next(
                    (
                        match for match in matches
                        if owner_handle and _clawhub_match_owner(match) == owner_handle
                    ),
                    matches[0] if not owner_handle else None,
                )
                ref = (selected or {}).get("slug", "")
                if ref:
                    resp = _client.get(f"{CLAWHUB_BASE}/skills/{ref}")
                else:
                    raise HTTPException(404, f"ClawHub 有多个同名 Skill「{slug}」，请指定作者")

        if resp.status_code != 200:
            raise HTTPException(404, f"ClawHub 未找到：{slug}")

        data = resp.json()
        skill_data = data.get("skill", data)
        description = (skill_data.get("summary") or skill_data.get("description") or "")
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


def _clawhub_match_owner(match: dict) -> str:
    owner = match.get("ownerHandle") or match.get("owner") or match.get("publisher") or ""
    if isinstance(owner, dict):
        return str(owner.get("handle") or owner.get("displayName") or "")
    return str(owner).lstrip("@").split("/")[0]


def _get_skillsmp_skill(slug: str, github_url: str = "") -> dict:
    """获取 SkillsMP Skill 详情。

    先搜索 SkillsMP 获取元信息（名称、描述、githubUrl），再从 GitHub 获取完整 SKILL.md。
    """
    name = slug
    description = ""
    skill_url = ""

    # 1. 尝试从 github URL 提取更好的搜索关键词
    search_q = slug
    if github_url:
        # 取 GitHub URL 的最后一段作为名称/搜索词
        parts = github_url.rstrip("/").split("/")
        if parts:
            search_q = parts[-1]  # e.g. "drawio-skill"

    # 2. 搜索 SkillsMP 匹配元信息
    try:
        search_resp = _client.get(
            f"{SKILLSMP_BASE}/skills/search",
            params={"q": search_q, "limit": 30},
        )
        if search_resp.status_code == 200:
            search_data = search_resp.json()
            skills = search_data.get("data", {}).get("skills", [])
            for sk in skills:
                if sk.get("id") == slug or sk.get("skillUrl", "").endswith(slug):
                    name = sk.get("name", slug)
                    description = sk.get("description", "")
                    if not github_url:
                        github_url = sk.get("githubUrl", "")
                    skill_url = sk.get("skillUrl", "")
                    break
    except Exception:
        pass

    # 3. 如果搜索没找到名字，从 github_url 提取
    if name == slug and github_url:
        parts = github_url.rstrip("/").split("/")
        if parts:
            name = parts[-1]

    # 4. 从 GitHub 获取完整内容
    if github_url:
        content = _fetch_github_skill(github_url)
        if content:
            return {
                "name": name, "description": description,
                "source": "skillsmp", "slug": slug,
                "version": "", "files": [], "content": content,
            }

    # 5. GitHub 获取失败，返回元信息
    if description:
        return {
            "name": name, "description": description,
            "source": "skillsmp", "slug": slug,
            "version": "", "files": [],
            "content": f"# {name}\n\n{description}\n\nSkill URL: {skill_url}\nGitHub: {github_url}",
        }

    raise HTTPException(404, f"SkillsMP 未找到：{slug}")


# ── 安装 Skill ─────────────────────────────────────────────────────────────


@router.post("/install")
def install_skill(payload: dict):
    """从市场下载原始 SKILL.md 并保存到本地 skills/ 目录，
    同时下载配套文件（scripts/, references/ 等）。"""
    source = str(payload.get("source", ""))
    slug = str(payload.get("slug", ""))
    github_url = str(payload.get("github_url", ""))
    owner_handle = str(payload.get("owner_handle", ""))

    if not source or not slug:
        raise HTTPException(400, "source 和 slug 不能为空")

    # 1. 下载原始内容
    detail = get_skill_detail(source, slug, url=github_url, owner=owner_handle)
    content = detail.get("content", "")
    name = detail.get("name", slug)
    description = detail.get("description", "")

    # 2. 尝试获取配套文件（ClawHub ZIP 或 GitHub 仓库）
    extra_files = 0
    if source == "clawhub":
        extra_files = _download_and_extract_clawhub(slug, name)
        if not content:
            # SKILL.md 可能从 ZIP 中提取出来了
            skill_dir = SKILLS_DIR / name
            md_file = skill_dir / "SKILL.md"
            if md_file.is_file():
                content = md_file.read_text(encoding="utf-8")
    elif source == "skillsmp" and github_url:
        extra_files = _download_github_extras(github_url, name)

    if not content:
        raise HTTPException(400, "无法获取 Skill 内容")

    # 3. 如果没有 frontmatter，简单包一层
    if not content.strip().startswith("---"):
        content = f"---\nname: {name}\ndescription: {description}\n---\n\n{content}"

    # 4. 保存到 skills/<name>/SKILL.md
    skill_dir = SKILLS_DIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    from .skill_compatibility import scan_skill
    compatibility = scan_skill(name, trigger="install")

    # 5. 列出最终文件
    installed_files = [
        str(p.relative_to(skill_dir))
        for p in skill_dir.rglob("*") if p.is_file()
    ]

    return {
        "installed": True,
        "name": name,
        "path": str(skill_dir.relative_to(SKILLS_DIR.parent)),
        "source": source,
        "files": installed_files,
        "extra_files_downloaded": extra_files,
        "compatibility": compatibility,
    }


@router.post("/skills/{name}/compatibility/scan")
def rescan_skill_compatibility(name: str):
    """Rebuild the index and statically rescan one installed Skill."""
    from my_agent_next.skills._loader import rebuild_index
    from .skill_compatibility import scan_skill

    skill_dir = SKILLS_DIR / name
    if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
        raise HTTPException(404, f"Skill「{name}」不存在")
    rebuild_index()
    try:
        return scan_skill(name, trigger="manual")
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc))


# ── 卸载 Skill ─────────────────────────────────────────────────────────────

# 内置 Skill，不允许删除
PROTECTED_SKILLS = {"review-agent", "skill-creator", "skill-installer", "user-memory"}


@router.delete("/skills/{name}")
def uninstall_skill(name: str):
    """卸载一个已安装的 Skill。

    保护规则：
    1. 四个内置 Skill（review-agent, skill-creator, skill-installer, user-memory）不允许删除
    2. 如果 Skill 正被 Agent 使用，返回使用该 Skill 的 Agent 列表，要求先解绑
    """
    name = name.strip()
    if not name:
        raise HTTPException(400, "Skill 名称不能为空")

    # 1. 检查内置 Skill
    if name in PROTECTED_SKILLS:
        raise HTTPException(400, f"「{name}」是内置 Skill，不允许删除")

    # 2. 检查 Skill 是否存在
    skill_dir = SKILLS_DIR / name
    if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
        raise HTTPException(404, f"Skill「{name}」不存在")

    # 3. 检查是否有 Agent 正在使用
    from .agent_profile_repository import AgentProfileRepository
    agent_repo = AgentProfileRepository()
    using_agents = [
        a.name or a.id
        for a in agent_repo.list()
        if name in (a.skills or [])
    ]
    if using_agents:
        raise HTTPException(
            400,
            f"无法删除「{name}」，以下 Agent 正在使用该 Skill：\n"
            + "、".join(using_agents)
            + "\n请先在 Agent 管理中取消绑定后再删除。",
        )

    # 4. 删除目录
    import shutil
    try:
        shutil.rmtree(skill_dir)
        return {"deleted": True, "name": name}
    except Exception as exc:
        raise HTTPException(500, f"删除失败：{exc}")


def _download_and_extract_clawhub(slug: str, name: str) -> int:
    """从 ClawHub 下载 Skill ZIP 并提取所有文件到 skills/<name>/。"""
    try:
        resp = _client.get(f"{CLAWHUB_BASE}/download", params={"slug": slug})
        if resp.status_code != 200:
            return 0
        skill_dir = SKILLS_DIR / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for info in zf.filelist:
                if info.is_dir():
                    continue
                filename = info.filename
                # 去掉 ZIP 中的顶层目录前缀（如 drawio-main/SKILL.md → SKILL.md）
                parts = filename.replace("\\", "/").split("/")
                if len(parts) > 1 and parts[0].lower() in (name.lower(), f"{name.lower()}-main", f"{name.lower()}-master"):
                    rel_path = "/".join(parts[1:])
                else:
                    rel_path = filename
                dest = (skill_dir / rel_path).resolve()
                try:
                    dest.relative_to(skill_dir.resolve())
                except ValueError:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    content = zf.read(info.filename)
                    dest.write_bytes(content)
                    count += 1
                except Exception:
                    pass
        return count
    except Exception as exc:
        print(f"[marketplace] 下载 ClawHub ZIP 失败: {exc}")
        return 0


def _download_github_extras(github_url: str, name: str) -> int:
    """从 GitHub 仓库递归下载 Skill 目录的全部文件（含 scripts/, data/, styles/ 等）。"""
    if not github_url:
        return 0
    try:
        import re
        # 解析 GitHub URL: /tree/<branch>/<path> 或 /blob/<branch>/<path>
        match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+)/(?:tree|blob)/([^/]+)/(.+)$",
            github_url,
        )
        if not match:
            return 0
        owner, repo, branch, path = match.groups()
        path = path.rstrip("/")

        skill_dir = SKILLS_DIR / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        count = _fetch_github_dir(api_url, skill_dir)
        return count
    except Exception as exc:
        print(f"[marketplace] GitHub 全量下载失败: {exc}")
        return 0


def _fetch_github_dir(api_url: str, dest_dir: Path) -> int:
    """递归下载 GitHub 目录的全部内容到 dest_dir。返回下载的文件数。

    优先使用 GitHub API；如果 API 限流（403），降级为解析 HTML 页面。
    """
    items = _github_api_list(api_url)
    if items is None:
        # API 失败，尝试解析 HTML
        html_url = api_url.replace("api.github.com/repos", "github.com")
        html_url = re.sub(r"/contents/", "/tree/", html_url)
        html_url = re.sub(r"\?ref=", "/", html_url)
        owner, repo, branch, path = _parse_github_api_url(api_url)
        if owner:
            items = _github_html_list(owner, repo, branch, path)

    if not items:
        return 0

    count = 0
    dest_dir.mkdir(parents=True, exist_ok=True)

    for item in items:
        name = item.get("name", "")
        if item.get("type") == "file":
            # 跳过 SKILL.md —— 已由 install_skill 写入（含 frontmatter 处理）
            if name == "SKILL.md":
                continue
            download_url = item.get("download_url") or item.get("html_url", "")
            if download_url:
                try:
                    file_resp = _client.get(download_url)
                    if file_resp.status_code == 200:
                        (dest_dir / name).write_bytes(file_resp.content)
                        count += 1
                except Exception:
                    pass
        elif item.get("type") == "dir":
            sub_url = item.get("url") or item.get("html_url", "")
            if sub_url:
                count += _fetch_github_dir(sub_url, dest_dir / name)

    return count


def _github_api_list(api_url: str) -> list | None:
    """通过 GitHub API 获取目录列表。失败返回 None。"""
    try:
        resp = _client.get(api_url, headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MyAgentNext/1.0",
        })
        if resp.status_code == 200:
            items = resp.json()
            if isinstance(items, list):
                return items
    except Exception:
        pass
    return None


def _parse_github_api_url(api_url: str) -> tuple:
    """解析 GitHub API URL: (owner, repo, branch, path)。"""
    import re
    m = re.match(
        r"https?://api\.github\.com/repos/([^/]+)/([^/]+)/contents/(.+?)(?:\?ref=(.+))?$",
        api_url,
    )
    if m:
        owner, repo, path = m.group(1), m.group(2), m.group(3)
        branch = m.group(4) or "main"
        return owner, repo, branch, path
    return None, None, None, None


def _github_html_list(owner: str, repo: str, branch: str, path: str) -> list:
    """解析 GitHub HTML 页面获取目录文件列表（API 限流时的降级方案）。"""
    try:
        html_url = f"https://github.com/{owner}/{repo}/tree/{branch}/{path}"
        resp = _client.get(html_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        if resp.status_code != 200:
            return []

        import re
        text = resp.text

        items = []
        # 提取文件/目录行：<a href="/owner/repo/blob|tree/branch/path/filename"
        pattern = re.compile(
            r'href="/' + re.escape(owner) + r'/' + re.escape(repo)
            + r'/(blob|tree)/' + re.escape(branch) + r'/'
            + re.escape(path) + r'/([^"]+)"',
        )
        seen = set()
        for match in pattern.finditer(text):
            entry_type = "file" if match.group(1) == "blob" else "dir"
            name = match.group(2).split("/")[0]  # 只取第一级
            if name in seen:
                continue
            seen.add(name)

            # 构建 raw/download URL
            if entry_type == "file":
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}/{name}"
                sub_url = raw_url
            else:
                sub_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}/{name}?ref={branch}"

            items.append({
                "name": name,
                "type": entry_type,
                "download_url": raw_url if entry_type == "file" else None,
                "url": sub_url,
                "html_url": f"https://github.com/{owner}/{repo}/{entry_type}/{branch}/{path}/{name}",
            })

        return items
    except Exception as exc:
        print(f"[marketplace] HTML 解析失败: {exc}")
        return []


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
