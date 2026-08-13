# app/tools/bash.py — 使用当前平台的原生命令行执行命令
# =============================================================================

import os
import subprocess
import sys

from langchain_core.tools import tool

from .base import WORKSPACE_ROOT, check_bash_command, is_dangerous_command, truncate_output


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
    """使用当前平台的原生命令行执行命令并返回输出。

    Windows 使用 Windows PowerShell；Linux/macOS 使用 /bin/bash 或 /bin/sh。
    Windows 不调用 WSL、Git Bash 或 bash.exe。

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
        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
        }
        # 子命令中的 `python` 必须与运行后端的解释器一致。后端从项目
        # .venv 启动时，这会把 .venv/Scripts（Linux 为 .venv/bin）置于 PATH 首位。
        runtime_bin = os.path.dirname(sys.executable)
        path_separator = ";" if os.name == "nt" else ":"
        env["PATH"] = runtime_bin + path_separator + env.get("PATH", "")
        if os.name == "nt":
            # 始终使用 Windows 原生命令行，避免 PATH 中的 bash.exe 启动 WSL。
            reg_path = _windows_registry_path()
            if reg_path:
                # 保留服务进程（尤其是项目 .venv）的 PATH 优先级，只在末尾补充
                # 服务启动后新安装的 Windows CLI 路径。
                env["PATH"] = env["PATH"] + ";" + reg_path
            utf8_prefix = (
                "[Console]::InputEncoding=[Text.UTF8Encoding]::new();"
                "[Console]::OutputEncoding=[Text.UTF8Encoding]::new();"
                "$OutputEncoding=[Text.UTF8Encoding]::new();"
            )
            result = subprocess.run(
                [
                    "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-Command", utf8_prefix + command,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(WORKSPACE_ROOT),
                env=env,
            )
        else:
            shell = "/bin/bash" if os.path.isfile("/bin/bash") else "/bin/sh"
            result = subprocess.run(
                [shell, "-lc", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
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
