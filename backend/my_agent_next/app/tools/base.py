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
    """检查路径是否在工作目录内（拒绝 .. 越界）。"""
    try:
        resolved = (WORKSPACE_ROOT / path).resolve()
        return resolved.is_relative_to(WORKSPACE_ROOT)
    except (ValueError, OSError):
        return False


def safe_resolve(path: str) -> Path:
    """安全解析路径，越界则抛异常。"""
    resolved = (WORKSPACE_ROOT / path).resolve()
    if not resolved.is_relative_to(WORKSPACE_ROOT):
        raise PermissionError(f"路径越界：{path}")
    return resolved


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
