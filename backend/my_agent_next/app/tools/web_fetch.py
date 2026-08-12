# app/tools/web_fetch.py — 获取网页内容
# =============================================================================

import httpx
from langchain_core.tools import tool

from .base import truncate_output


@tool
def web_fetch(url: str) -> str:
    """获取网页内容并转换为纯文本。用于读取文档、API 响应等。

    Args:
        url: 要获取的网页 URL（支持 http/https）
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return f"错误：不支持的协议，请使用 http:// 或 https:// 开头的 URL"
    try:
        client = httpx.Client(timeout=15.0, follow_redirects=True)
        resp = client.get(url, headers={"User-Agent": "MyAgentNext/1.0"})
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "text/html" in content_type:
            # 简单 HTML → 文本：移除标签
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", resp.text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return truncate_output(text)
        elif "application/json" in content_type:
            import json
            data = resp.json()
            return truncate_output(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            return truncate_output(resp.text[:8000])
    except httpx.HTTPStatusError as e:
        return f"HTTP 错误 {e.response.status_code}: {url}"
    except httpx.TimeoutException:
        return f"请求超时: {url}"
    except Exception as e:
        return f"请求失败: {e}"
