# app/tools/web_fetch.py — 获取网页内容并转为 Markdown
# =============================================================================

import html2text
import httpx
from langchain_core.tools import tool

from .base import truncate_output

# 初始化 html2text 转换器
_h = html2text.HTML2Text()
_h.ignore_links = False
_h.ignore_images = True
_h.ignore_emphasis = False
_h.body_width = 0           # 不自动换行
_h.protect_links = True
_h.unicode_snob = True      # 保留 Unicode 字符


@tool
def web_fetch(url: str, prompt: str = "") -> str:
    """获取网页内容并转换为 Markdown 格式。用于阅读文档、API 响应、技术文章等。

    Args:
        url: 要获取的网页 URL（支持 http/https）
        prompt: 可选，从页面内容中提取特定信息的提示。留空则返回完整内容。
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return f"错误：不支持的协议，请使用 http:// 或 https:// 开头的 URL"

    try:
        client = httpx.Client(timeout=20.0, follow_redirects=True)
        resp = client.get(url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        # JSON 响应直接格式化
        if "application/json" in content_type:
            import json
            data = resp.json()
            return truncate_output(json.dumps(data, ensure_ascii=False, indent=2))

        # 纯文本直接返回
        if "text/plain" in content_type:
            return truncate_output(resp.text)

        # HTML → Markdown
        if "text/html" in content_type or not content_type:
            markdown = _h.handle(resp.text)
            result = markdown.strip()

            # 如果指定了 prompt，尝试用简单的关键词匹配高亮相关段落
            # （完整 AI 提取由 LLM 在拿到结果后自行完成）
            if prompt and len(result) > 4000:
                # 保留前 4000 字符 + 提示
                result = (
                    result[:4000]
                    + f"\n\n---\n⚠️ 内容较长（共 {len(result)} 字符），已截断。"
                    + f"\n提示：请关注与「{prompt[:100]}」相关的部分。"
                    + "\n如需完整内容，可使用更精确的 URL 分段获取。"
                )

            return truncate_output(result)

        # 其他类型：返回原始文本（截断）
        return truncate_output(resp.text[:8000])

    except httpx.HTTPStatusError as e:
        return f"HTTP 错误 {e.response.status_code}: {url}"
    except httpx.TimeoutException:
        return f"请求超时（20 秒）: {url}"
    except Exception as e:
        return f"请求失败: {e}"
