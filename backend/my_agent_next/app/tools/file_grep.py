# app/tools/file_grep.py — 搜索文件内容（ripgrep 风格）
# =============================================================================

import re

from langchain_core.tools import tool

from .base import WORKSPACE_ROOT, safe_resolve, truncate_output


@tool
def grep(pattern: str, path: str = ".") -> str:
    """在文件中搜索匹配的行（支持正则表达式）。

    Args:
        pattern: 正则表达式模式
        path: 搜索目录或文件路径（默认当前工作目录）
    """
    try:
        base = safe_resolve(path)
        if not base.exists():
            return f"错误：路径不存在 - {path}"

        files = [base] if base.is_file() else sorted(base.rglob("*"))
        # 跳过二进制文件和隐藏目录
        skip_exts = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
                     ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz"}
        skip_dirs = {"__pycache__", ".git", ".venv", "node_modules", ".idea", ".vscode"}

        compiled = re.compile(pattern)
        results = []
        matched_files = 0

        for f in files:
            if not f.is_file():
                continue
            if f.suffix.lower() in skip_exts:
                continue
            if any(d in f.parts for d in skip_dirs):
                continue
            if matched_files >= 50:
                break
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            file_matched = False
            for i, line in enumerate(content.split("\n"), 1):
                if compiled.search(line):
                    if not file_matched:
                        # 显示路径：项目内用相对路径，项目外用绝对路径
                        try:
                            display = f.relative_to(WORKSPACE_ROOT)
                        except ValueError:
                            display = str(f)
                        results.append(f"\n{display}:")
                        file_matched = True
                        matched_files += 1
                    results.append(f"  {i}: {line[:200]}")
                    if len(results) > 500:
                        results.append("\n... [结果截断]")
                        return truncate_output("\n".join(results))
        if not results:
            return f"无匹配：{pattern}"
        return truncate_output("\n".join(results))
    except PermissionError as e:
        return f"权限错误：{e}"
    except re.error as e:
        return f"正则表达式错误：{e}"
    except Exception as e:
        return f"搜索失败：{e}"
