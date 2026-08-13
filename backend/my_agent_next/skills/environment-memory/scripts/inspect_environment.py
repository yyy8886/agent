#!/usr/bin/env python3
"""Read-only, secret-safe runtime environment inspection for Mabel."""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from pathlib import Path

SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
COMMANDS = ("python", "python3", "git", "drawio", "draw.io", "bash", "pwsh", "powershell")

def redact_environment() -> dict[str, object]:
    result: dict[str, object] = {}
    for name in sorted(os.environ):
        if any(marker in name.upper() for marker in SECRET_MARKERS):
            result[name] = {"configured": bool(os.environ.get(name))}
        elif name in {"LANG", "LC_ALL", "LC_CTYPE", "PYTHONIOENCODING", "SHELL", "COMSPEC", "WSL_DISTRO_NAME", "WSL_INTEROP"}:
            result[name] = os.environ[name]
    return result

def main() -> None:
    cwd = Path.cwd().resolve()
    workspace = os.environ.get("AGENT_WORKSPACE") or str(cwd)
    report = {
        "schema_version": 1,
        "host": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "runtime": {"system": platform.system(), "python": sys.executable, "python_version": platform.python_version()},
        "shell": {"shell": os.environ.get("SHELL") or os.environ.get("COMSPEC") or "unknown", "wsl": bool(os.environ.get("WSL_DISTRO_NAME"))},
        "workspace": workspace,
        "path_forms": {"cwd": str(cwd), "workspace": str(Path(workspace).expanduser())},
        "commands": {name: shutil.which(name) for name in COMMANDS},
        "capabilities": {"read_cwd": os.access(cwd, os.R_OK), "write_cwd": os.access(cwd, os.W_OK), "gui_display": bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))},
        "environment": redact_environment(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
