# app/tools/web_search.py — 搜索网页
# =============================================================================

from langchain_core.tools import tool

from .base import truncate_output


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """搜索互联网获取最新信息。当需要查找文档、教程、新闻、技术方案时使用。

    Args:
        query: 搜索关键词（支持中英文）
        max_results: 最多返回几条结果（默认 5，最大 10）
    """
    max_results = min(max(1, max_results), 10)
    query = query.strip()
    if not query:
        return "错误：搜索关键词不能为空"

    results = []

    # 方案 A：ddgs（原 duckduckgo_search）
    try:
        from ddgs import DDGS

        ddgs = DDGS()
        search_results = list(ddgs.text(query, max_results=max_results))

        if search_results:
            results.append(f"搜索「{query}」共 {len(search_results)} 条结果：\n")
            for i, r in enumerate(search_results, 1):
                title = r.get("title", "无标题")
                href = r.get("href", "")
                body = r.get("body", "")
                if len(body) > 300:
                    body = body[:300] + "..."
                results.append(f"{i}. **{title}**\n   {body}\n   {href}")

        ddgs.close()
    except Exception:
        pass

    # 方案 B：降级到 DuckDuckGo Instant Answer API
    if not results:
        try:
            import httpx
            client = httpx.Client(timeout=10.0)
            resp = client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "no_redirect": 1},
                headers={"User-Agent": "MyAgentNext/1.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                abstract = data.get("AbstractText", "")
                if abstract:
                    results.append(f"摘要: {abstract}\n来源: {data.get('AbstractURL', '')}")

                topics = data.get("RelatedTopics", [])
                for topic in topics[:max_results]:
                    if isinstance(topic, dict):
                        text = topic.get("Text", "")
                        url = topic.get("FirstURL", "")
                        if text:
                            results.append(f"- {text}\n  {url}")
        except Exception:
            pass

    if not results:
        encoded = query.replace(" ", "+")
        results.append(
            f"搜索「{query}」未返回结果。\n"
            + f"建议：1) 简化关键词重试 2) 直接访问 https://www.google.com/search?q={encoded}"
        )

    return truncate_output("\n\n".join(results))
