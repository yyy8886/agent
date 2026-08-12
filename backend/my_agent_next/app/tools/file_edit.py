# app/tools/file_edit.py — 精确字符串替换编辑文件
# =============================================================================

from langchain_core.tools import tool

from .base import safe_resolve


@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """在文件中进行精确字符串替换。old_string 必须在文件中唯一匹配。

    Args:
        path: 文件路径（相对于工作目录）
        old_string: 要被替换的文本（必须精确匹配）
        new_string: 替换后的文本
    """
    try:
        resolved = safe_resolve(path)
        if not resolved.is_file():
            return f"错误：文件不存在 - {path}"
        content = resolved.read_text(encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            return f"错误：未找到要替换的文本"
        if count > 1:
            return f"错误：old_string 匹配了 {count} 处（需要唯一匹配）"
        new_content = content.replace(old_string, new_string, 1)
        resolved.write_text(new_content, encoding="utf-8")
        return f"已编辑：{path}（替换了 1 处）"
    except PermissionError as e:
        return f"权限错误：{e}"
    except Exception as e:
        return f"编辑失败：{e}"
