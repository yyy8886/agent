# app/tools/file_read.py — 读取文件内容
# =============================================================================

from langchain_core.tools import tool

from .base import safe_resolve, truncate_output


@tool
def read_file(path: str, offset: int = 0, limit: int = 2000) -> str:
    """读取文件内容。可以读取绝对路径（如 C:\\Users\\...）或相对路径。

    Args:
        path: 文件路径（支持绝对路径和相对路径）
        offset: 从第几行开始读（默认 0）
        limit: 最多读多少行（默认 2000，最大 5000）
    """
    limit = min(max(0, limit), 5000)
    try:
        resolved = safe_resolve(path)
        if not resolved.is_file():
            return f"错误：文件不存在 - {path}"

        # 检查文件大小，超过 1MB 只读前 100KB
        file_size = resolved.stat().st_size
        if file_size > 1_000_000:
            # 大文件：只读文本内容的前 100KB
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(100_000)
            line_count_estimate = file_size // 80  # 粗略估计
            return (
                content
                + f"\n\n... [文件过大（{file_size:,} 字节，约 {line_count_estimate:,} 行），"
                + f"仅显示前 100KB。请用 offset/limit 参数分段读取]"
            )

        content = resolved.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        total_lines = len(lines)

        if offset > 0:
            lines = lines[offset:]
        if limit > 0 and len(lines) > limit:
            lines = lines[:limit]
            lines.append(f"\n... [文件共 {total_lines} 行，已显示第 {offset+1}-{offset+limit} 行]")
        return "\n".join(lines)
    except PermissionError as e:
        return f"权限错误：{e}"
    except Exception as e:
        return f"读取失败：{e}"
