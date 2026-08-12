# app/tools/base.py — 工具系统基础：安全校验 + 工作目录管理
# =============================================================================

import os
from enum import Enum
from pathlib import Path
from dataclasses import dataclass

# 工作目录 = my_agent_next 项目根目录（也可以是用户 home 目录）
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.resolve()


class PermissionMode(str, Enum):
    MANUAL = "manual"    # 每次工具调用需确认
    PLAN = "plan"        # 审批计划后自动执行
    AUTO = "auto"        # 全自动


# 命令黑名单（即使在自动模式下也阻止）
BASH_BLACKLIST = [
    "rm -rf /", "rm -rf ~", "rm -rf .",
    "sudo ", "mkfs", "dd if=", ":(){ :|:& };:",
    "chmod 777 /", "chmod -R 777 /",
    "> /dev/sda", "format c:",
]

# 危险命令（自动模式下需降级为手动确认）
BASH_DANGEROUS = ["rm ", "mv ", "chmod ", "chown ", "shutdown", "reboot"]


def is_safe_path(path: str) -> bool:
    """检查路径是否在允许范围内。绝对路径直接解析，相对路径基于 WORKSPACE_ROOT。"""
    try:
        safe_resolve(path)
        return True
    except PermissionError:
        return False


def safe_resolve(path: str) -> Path:
    """安全解析路径。

    - 绝对路径：直接解析，允许访问用户目录及子目录
    - 相对路径：基于 WORKSPACE_ROOT 解析
    """
    p = Path(path)
    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (WORKSPACE_ROOT / path).resolve()

    # 允许的范围：
    # 1. WORKSPACE_ROOT（项目目录）
    # 2. 用户 Home 目录（含 Documents、Desktop、Downloads 等）
    home = Path.home()
    safe_roots = [WORKSPACE_ROOT, home]

    for root in safe_roots:
        try:
            if resolved == root or resolved.is_relative_to(root):
                return resolved
        except (ValueError, OSError):
            pass

    raise PermissionError(
        f"路径越界：{path}（仅允许访问 {WORKSPACE_ROOT} 和 {home} 下的文件）"
    )


def check_bash_command(command: str) -> tuple[bool, str]:
    """检查 bash 命令安全性。返回 (allowed, reason)。"""
    cmd_lower = command.lower().strip()
    for pattern in BASH_BLACKLIST:
        if pattern.lower() in cmd_lower:
            return False, f"命令被黑名单拦截：{pattern}"
    return True, ""


def is_dangerous_command(command: str) -> bool:
    """检查是否为危险命令（需要额外确认）。"""
    cmd_lower = command.lower().strip()
    return any(d in cmd_lower for d in BASH_DANGEROUS)


def truncate_output(text: str, max_chars: int = 8000) -> str:
    """截断过长的工具输出。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n... [截断，原长度 {len(text)} 字符]"
