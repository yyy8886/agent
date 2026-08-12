# skills/_loader.py — Skill 加载器
# =============================================================================
# 扫描 skills/ 目录下所有子目录，读取 SKILL.md 并解析 YAML frontmatter。
#
# 每个 Skill 目录结构：
#   skills/<name>/
#   ├── SKILL.md          # YAML frontmatter + markdown 指令
#   ├── references/       # 详细参考文档（可选，按需读取）
#   └── scripts/          # 辅助脚本（可选，LLM 通过 Bash 调用）
#
# 导出函数：
#   load_all()              → list[SkillInfo]  所有已安装 Skill
#   get(name)               → SkillInfo | None  按名查找
#   available_skill_choices() → list[dict]      给前端/agent_profile_service 用
# =============================================================================

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parent


@dataclass
class SkillInfo:
    """一个 Skill 的元信息和内容。"""
    name: str           # frontmatter name 字段
    description: str    # frontmatter description 字段
    path: Path          # Skill 目录路径
    content: str        # markdown 正文（不含 frontmatter）


def _parse_skill(skill_dir: Path) -> SkillInfo | None:
    """解析单个目录下的 SKILL.md，返回 SkillInfo 或 None。"""
    md_file = skill_dir / "SKILL.md"
    if not md_file.is_file():
        return None

    text = md_file.read_text(encoding="utf-8")

    # 解析 YAML frontmatter：两个 --- 之间
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return None

    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None

    body = match.group(2).strip()

    return SkillInfo(
        name=frontmatter.get("name", skill_dir.name),
        description=frontmatter.get("description", ""),
        path=skill_dir,
        content=body,
    )


def load_all() -> list[SkillInfo]:
    """扫描 skills/ 目录，返回所有已安装的 Skill。"""
    skills: list[SkillInfo] = []
    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("_") or entry.name.startswith("."):
            continue
        info = _parse_skill(entry)
        if info:
            skills.append(info)
    return skills


def get(name: str) -> SkillInfo | None:
    """按名称查找一个 Skill。"""
    skill_dir = SKILLS_DIR / name
    return _parse_skill(skill_dir)


def available_skill_choices() -> list[dict]:
    """返回 {name, description} 列表，供前端和 agent_profile_service 使用。"""
    return [{"name": s.name, "description": s.description} for s in load_all()]
