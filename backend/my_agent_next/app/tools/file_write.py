# app/tools/file_write.py — 写入文件
# =============================================================================

from langchain_core.tools import tool

from .base import safe_resolve


@tool
def write_file(path: str, content: str) -> str:
    """写入文件（覆盖已有文件）。创建新文件或覆盖已有文件。

    Args:
        path: 文件路径（相对于工作目录）
        content: 要写入的内容
    """
    try:
        resolved = safe_resolve(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"已写入：{path}（{len(content)} 字符）"
    except PermissionError as e:
        return f"权限错误：{e}"
    except Exception as e:
        return f"写入失败：{e}"
