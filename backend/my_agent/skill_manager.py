"""Controlled installer for Agent Skills used by my_agent."""

import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import quote, urlparse


SKILLS_DIR = Path(__file__).resolve().parent / "skills"
REGISTRY_FILE = SKILLS_DIR / "registry.json"
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024

# Marketplace pages are indexes, not executable package endpoints. Resolve only
# entries reviewed by this project; more adapters can be added explicitly.
KNOWN_MARKETPLACE_SOURCES = {
    "https://skillsmp.com/skills/agents365-ai-drawio-skill-skills-drawio-skill-skill-md":
        "https://github.com/Agents365-ai/drawio-skill",
    "https://clawhub.ai/agents365-ai/drawio-pro-skill":
        "https://github.com/Agents365-ai/drawio-skill",
}

KNOWN_MARKET_SKILLS = [
    {
        "name": "drawio-skill",
        "description": "生成、校验和导出可编辑 draw.io 图表。",
        "source": "SkillsMP",
        "url": "https://skillsmp.com/skills/agents365-ai-drawio-skill-skills-drawio-skill-skill-md",
    },
    {
        "name": "drawio-pro-skill",
        "description": "ClawHub 上的 draw.io 专业绘图 Skill。",
        "source": "ClawHub",
        "url": "https://clawhub.ai/agents365-ai/drawio-pro-skill",
    },
]


def _load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {"skills": {}}
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"skills": {}}


def _save_registry(registry: dict) -> None:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_skills() -> list[dict]:
    return list(_load_registry().get("skills", {}).values())


def search_market_skills(query: str) -> dict:
    """Search the local reviewed catalog and provide marketplace search URLs."""
    cleaned = query.strip().lower()
    matches = [
        item for item in KNOWN_MARKET_SKILLS
        if not cleaned or cleaned in item["name"].lower() or cleaned in item["description"].lower()
    ]
    encoded = quote(query.strip())
    return {
        "results": matches,
        "external_search": {
            "skillsmp": f"https://skillsmp.com/search?q={encoded}",
            "clawhub": f"https://clawhub.ai/skills?search={encoded}",
        },
    }


def _resolve_github_source(source_url: str) -> tuple[str, str, str]:
    normalized = source_url.rstrip("/")
    normalized = KNOWN_MARKETPLACE_SOURCES.get(normalized, normalized)
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("当前只安装 GitHub Skill，或已审核的 SkillsMP/ClawHub 条目。")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub 地址必须包含 owner/repository。")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not owner.replace("-", "").isalnum() or not repo.replace("-", "").isalnum():
        raise ValueError("GitHub owner/repository 格式无效。")
    return owner, repo, normalized


def install_skill(source_url: str) -> str:
    """Download and register a Skill without enabling bundled scripts."""
    owner, repo, resolved_source = _resolve_github_source(source_url)
    skill_name = repo.lower()
    destination = SKILLS_DIR / skill_name
    if destination.exists():
        return f"安装失败：Skill {skill_name} 已存在。"

    archive_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"
    request = urllib.request.Request(archive_url, headers={"User-Agent": "my-agent-skill-manager/0.1"})

    with tempfile.TemporaryDirectory(prefix="my-agent-skill-") as temp_text:
        temp_dir = Path(temp_text)
        archive_file = temp_dir / "skill.zip"
        with urllib.request.urlopen(request, timeout=30) as response:
            content_length = int(response.headers.get("Content-Length", "0") or 0)
            if content_length > MAX_DOWNLOAD_BYTES:
                raise ValueError("Skill 压缩包超过 25 MB 限制。")
            data = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise ValueError("Skill 压缩包超过 25 MB 限制。")
        archive_file.write_bytes(data)

        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(archive_file) as archive:
            for member in archive.infolist():
                member_path = (extract_dir / member.filename).resolve()
                if extract_dir.resolve() not in member_path.parents and member_path != extract_dir.resolve():
                    raise ValueError("Skill 压缩包包含越界路径。")
            archive.extractall(extract_dir)

        candidates = list(extract_dir.rglob("SKILL.md"))
        if not candidates:
            raise ValueError("仓库中没有找到 SKILL.md。")
        skill_file = min(candidates, key=lambda path: len(path.parts))
        source_dir = skill_file.parent
        shutil.copytree(source_dir, destination)

    registry = _load_registry()
    registry.setdefault("skills", {})[skill_name] = {
        "name": skill_name,
        "source": source_url,
        "resolved_source": resolved_source,
        "enabled": False,
        "globally_blocked": False,
        "scripts_allowed": False,
        "path": str(destination),
    }
    _save_registry(registry)
    return f"Skill {skill_name} 已安装但未启用；自带脚本默认禁止执行。"


def set_skill_enabled(skill_name: str, enabled: bool) -> str:
    registry = _load_registry()
    skills = registry.setdefault("skills", {})
    if skill_name not in skills:
        return f"操作失败：未安装 Skill {skill_name}。"
    skills[skill_name]["enabled"] = enabled
    _save_registry(registry)
    state = "启用" if enabled else "禁用"
    return f"Skill {skill_name} 已{state}；自带脚本仍禁止自动执行。"


def set_skill_globally_blocked(skill_name: str, blocked: bool) -> str:
    registry = _load_registry()
    skills = registry.setdefault("skills", {})
    if skill_name not in skills:
        return f"操作失败：未安装 Skill {skill_name}。"
    skills[skill_name]["globally_blocked"] = blocked
    if blocked:
        skills[skill_name]["enabled"] = False
    _save_registry(registry)
    return f"Skill {skill_name} 已{'全局封印' if blocked else '解除全局封印'}。"


def skill_is_available(skill_name: str) -> bool:
    skill = _load_registry().get("skills", {}).get(skill_name)
    if skill is None:
        # Built-in skills are controlled by config.yaml and have no registry item.
        return True
    return bool(skill.get("enabled")) and not bool(skill.get("globally_blocked"))


def load_enabled_skill_instructions(allowed_names: set[str] | None = None) -> str:
    sections = []
    for skill in list_skills():
        if not skill.get("enabled"):
            continue
        if skill.get("globally_blocked"):
            continue
        if allowed_names is not None and skill["name"] not in allowed_names:
            continue
        skill_file = Path(skill["path"]) / "SKILL.md"
        if skill_file.exists():
            text = skill_file.read_text(encoding="utf-8")[:20_000]
            sections.append(f"# Skill: {skill['name']}\n{text}")
    return "\n\n".join(sections)
