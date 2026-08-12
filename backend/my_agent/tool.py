"""In-process LangChain tools.

Put small tools here when they belong to the Agent process. Tools that should be
reusable by other hosts belong in my_agent/mcp instead.
"""

import json
import platform
from pathlib import Path

from langchain_core.tools import tool

from my_agent.skill_manager import (
    install_skill,
    list_skills,
    set_skill_enabled,
)


PROFILE_FILE = Path(__file__).resolve().parent / "data" / "profile.json"
DEFAULT_IDENTITY = "主人"


def read_user_identity() -> str:
    """Read the persisted user identity, falling back to 主人."""
    if not PROFILE_FILE.exists():
        return DEFAULT_IDENTITY
    try:
        data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_IDENTITY
    identity = str(data.get("identity", "")).strip()
    return identity or DEFAULT_IDENTITY


@tool
def update_user_identity(identity: str) -> str:
    """修改并持久化用户希望梅贝尔使用的身份或称呼。"""
    cleaned = identity.strip()
    if not cleaned:
        return "修改失败：身份不能为空。"
    if len(cleaned) > 30:
        return "修改失败：身份不能超过 30 个字符。"

    PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_FILE.write_text(
        json.dumps({"identity": cleaned}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return f"身份已修改为：{cleaned}"


@tool
def install_agent_skill(source_url: str, approved: bool = False) -> str:
    """从受支持来源安装 Skill；只有主人明确确认时 approved 才能为 true。"""
    if not approved:
        return "等待主人确认：安装会下载第三方文件。请明确回复“确认安装”后再执行。"
    try:
        return install_skill(source_url)
    except Exception as exc:
        return f"Skill 安装失败：{exc}"


@tool
def enable_agent_skill(skill_name: str, enabled: bool, approved: bool = False) -> str:
    """启用或禁用已安装 Skill；需要主人明确确认。"""
    if not approved:
        return "等待主人确认：请明确回复确认启用或确认禁用。"
    return set_skill_enabled(skill_name, enabled)


@tool
def list_agent_skills() -> str:
    """列出当前 Agent 已安装 Skill 及启用状态。"""
    skills = list_skills()
    if not skills:
        return "当前没有安装任何 Skill。"
    return "\n".join(
        f"{item['name']}：{'已启用' if item['enabled'] else '未启用'}，"
        f"脚本自动执行={'允许' if item.get('scripts_allowed') else '禁止'}"
        for item in skills
    )


@tool
def get_runtime_platform() -> str:
    """返回当前 Python 运行平台和版本，用于本地运行环境排查。"""
    return f"{platform.system()} {platform.release()}, Python {platform.python_version()}"


LOCAL_TOOLS = [
    get_runtime_platform,
    update_user_identity,
    install_agent_skill,
    enable_agent_skill,
    list_agent_skills,
]
