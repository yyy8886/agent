# app/tools/bash.py — 执行 shell 命令
# =============================================================================

import subprocess

from langchain_core.tools import tool

from .base import WORKSPACE_ROOT, check_bash_command, is_dangerous_command, truncate_output


@tool
def run_bash(command: str, timeout: int = 30) -> str:
    """执行 shell 命令并返回输出。命令在工作目录中执行。

    Args:
        command: 要执行的 shell 命令
        timeout: 超时秒数（默认 30，最大 300）
    """
    # 安全检查
    allowed, reason = check_bash_command(command)
    if not allowed:
        return f"安全拦截：{reason}"

    timeout = min(max(timeout, 1), 300)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_ROOT),
            env={**__import__("os").environ, "PYTHONUNBUFFERED": "1"},
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[退出码: {result.returncode}]"
        return truncate_output(output.strip() or "(无输出)")
    except subprocess.TimeoutExpired:
        return f"命令超时（{timeout} 秒）: {command[:100]}"
    except Exception as e:
        return f"执行失败：{e}"
