# app/tools/file_glob.py — 文件模式匹配
# =============================================================================

from pathlib import Path

from langchain_core.tools import tool

from .base import WORKSPACE_ROOT, safe_resolve


@tool
def glob(pattern: str, path: str = ".") -> str:
    """使用 glob 模式匹配文件。支持 ** 递归匹配。

    Args:
        pattern: glob 模式（如 "**/*.py", "src/**/*.ts"）
        path: 搜索起始目录（默认当前工作目录）
    """
    try:
        base = safe_resolve(path)
        if not base.exists():
            return f"错误：目录不存在 - {path}"
        matches = sorted(base.glob(pattern))
        # 限制结果数量
        def _display(p: Path) -> str:
            try:
                return str(p.relative_to(WORKSPACE_ROOT))
            except ValueError:
                return str(p)

        if len(matches) > 200:
            lines = [_display(m) for m in matches[:200]]
            lines.append(f"\n... 共 {len(matches)} 个匹配，只显示前 200 个")
        else:
            lines = [_display(m) for m in matches]
        if not lines:
            return f"无匹配：{pattern}"
        return "\n".join(lines)
    except PermissionError as e:
        return f"权限错误：{e}"
    except Exception as e:
        return f"匹配失败：{e}"
