# app/tools/web_search.py — 搜索网页
# =============================================================================

import json
import httpx
from langchain_core.tools import tool

from .base import truncate_output

# DuckDuckGo Instant Answer API（免费，无需 key）
SEARCH_URL = "https://api.duckduckgo.com/"


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """搜索互联网获取信息。当需要查找最新资料、文档、解决方案时使用。

    Args:
        query: 搜索关键词
        max_results: 最多返回几条结果（默认 5，最大 10）
    """
    max_results = min(max(1, max_results), 10)
    query = query.strip()
    if not query:
        return "错误：搜索关键词不能为空"

    results = []

    # 尝试 DuckDuckGo API
    try:
        client = httpx.Client(timeout=10.0)
        resp = client.get(
            SEARCH_URL,
            params={"q": query, "format": "json", "no_html": 1, "no_redirect": 1},
            headers={"User-Agent": "MyAgentNext/1.0"},
        )
        if resp.status_code == 200:
            data = resp.json()

            # Abstract
            abstract = data.get("AbstractText", "")
            if abstract:
                results.append(f"摘要: {abstract}")

            # Related topics
            topics = data.get("RelatedTopics", [])
            for topic in topics[:max_results]:
                if isinstance(topic, dict):
                    text = topic.get("Text", "")
                    url = topic.get("FirstURL", "")
                    if text:
                        results.append(f"- {text}\n  {url}")

            # Results from External
            results_section = data.get("Results", [])
            for r in results_section[:max_results]:
                if isinstance(r, dict):
                    text = r.get("Text", "")
                    url = r.get("FirstURL", "")
                    if text:
                        results.append(f"- {text}\n  {url}")
    except Exception:
        pass

    # Fallback: 返回搜索建议
    if not results:
        results.append(f"未找到搜索结果，建议访问 https://www.google.com/search?q={query.replace(' ', '+')}")

    return truncate_output("\n\n".join(results))
