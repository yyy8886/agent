"""In-process LangChain tools.

Put small tools here when they belong to the Agent process. Tools that should be
reusable by other hosts belong in my_agent/mcp instead.
"""

import json
import platform
from pathlib import Path

from langchain_core.tools import tool


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
def get_runtime_platform() -> str:
    """返回当前 Python 运行平台和版本，用于本地运行环境排查。"""
    return f"{platform.system()} {platform.release()}, Python {platform.python_version()}"


LOCAL_TOOLS = [get_runtime_platform, update_user_identity]
