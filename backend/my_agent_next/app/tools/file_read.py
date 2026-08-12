# app/tools/file_read.py — 读取文件内容
# =============================================================================

from langchain_core.tools import tool

from .base import safe_resolve, truncate_output


@tool
def read_file(path: str, offset: int = 0, limit: int = 2000) -> str:
    """读取文件内容。

    Args:
        path: 文件路径（相对于工作目录）
        offset: 从第几行开始读（默认 0）
        limit: 最多读多少行（默认 2000）
    """
    try:
        resolved = safe_resolve(path)
        if not resolved.is_file():
            return f"错误：文件不存在 - {path}"
        content = resolved.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        if offset > 0:
            lines = lines[offset:]
        if limit > 0 and len(lines) > limit:
            lines = lines[:limit]
            lines.append(f"\n... [文件共 {len(content.split(chr(10)))} 行，截断显示]")
        return "\n".join(lines)
    except PermissionError as e:
        return f"权限错误：{e}"
    except Exception as e:
        return f"读取失败：{e}"
