# app/tools/bash.py — 执行 shell 命令
# =============================================================================

import os
import shutil
import subprocess

from langchain_core.tools import tool

from .base import WORKSPACE_ROOT, check_bash_command, is_dangerous_command, truncate_output


def _resolve_bash() -> str | None:
    """定位 git-bash 可执行文件。

    用 bash（而非 cmd.exe）执行命令有三个好处：
      1. 路径一致 —— bash 的 `pwd`/`ls` 输出 `/c/...`，`cd /c/...` 也能用；
         cmd.exe 下这些 Unix 工具虽在 PATH 里，但 `cd`/`copy` 又需要 Windows 语法，造成混乱。
      2. 多行命令（含 `python -c "..."` 内嵌换行与引号）能正确执行，
         cmd.exe 会逐行切分、破坏引号，导致静默无输出。
      3. 找到正确的 Python（venv 3.12），而非注册表 PATH 里的旧版本。
    找不到 bash 时退回 cmd.exe。
    """
    bash = shutil.which("bash")
    if bash:
        return bash
    for p in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ):
        if os.path.isfile(p):
            return p
    return None


_BASH = _resolve_bash()


def _windows_registry_path() -> str:
    """读取 Windows 注册表中的完整系统 PATH（系统级 + 用户级）。

    服务器进程可能是在 PATH 尚未包含新装工具（如 draw.io CLI）时启动的，
    其子进程（cmd.exe）会继承旧的 PATH。这里直接从注册表重新读取最新 PATH，
    保证 run_bash 能访问所有系统工具。
    """
    try:
        import winreg
    except ImportError:
        return ""
    parts = []
    for hive, key_path in (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, r"Environment"),
    ):
        try:
            with winreg.OpenKey(hive, key_path) as key:
                val, _ = winreg.QueryValueEx(key, "Path")
                if val:
                    parts.append(str(val))
        except OSError:
            continue
    return ";".join(parts)


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
        if _BASH and os.name == "nt":
            # 用 git-bash 执行：路径一致 + 多行命令正确 + 正确的 Python 版本。
            env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            result = subprocess.run(
                [_BASH, "-lc", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(WORKSPACE_ROOT),
                env=env,
            )
        else:
            env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            if os.name == "nt":
                # 合并注册表中的最新系统 PATH，确保能找到新安装的 CLI 工具
                reg_path = _windows_registry_path()
                if reg_path:
                    env["PATH"] = reg_path + ";" + os.environ.get("PATH", "")
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(WORKSPACE_ROOT),
                env=env,
            )
        output = result.stdout or ""
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[退出码: {result.returncode}]"
        return truncate_output(output.strip() or "(无输出)")
    except subprocess.TimeoutExpired:
        return f"命令超时（{timeout} 秒）: {command[:100]}"
    except Exception as e:
        return f"执行失败：{e}"
