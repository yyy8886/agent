# user_memory_service.py — 用户记忆业务逻辑层
# =============================================================================
# 两个核心职责：
#   1. get_memory_prompt() — 读取所有记忆，格式化为 system prompt 片段
#   2. extract_and_save() — 从本轮对话中提取关于用户的新事实，自动存入
#
# 工作原理（对用户透明）：
#   发消息前 → 把所有记忆注入 system prompt（"[关于用户] ..."）
#   AI 回复后 → 用 LLM 分析用户消息 + AI 回复，提取新事实，去重存入
#
# 项目中的位置（三层架构）：
#   chat_service.py → user_memory_service.py → user_memory_repository.py
# =============================================================================

import os
import re

from .user_memory_repository import UserMemoryRepository

MEMORY_EXTRACTION_PROMPT = """你是一个信息提取助手。从以下对话中提取**关于用户的新事实**，
每条事实一行，格式为"用户xxx"。只提取用户明确说出的或强烈暗示的个人信息，
例如：名字、偏好、习惯、职业、技能、过往经历、家庭情况等。

不要提取：
- 用户问的知识性问题（如"Python 装饰器是什么"）
- AI 的回答内容
- 泛泛的对话内容（如"你好""谢谢"）

如果本轮对话中没有新的用户个人信息，只回复"NONE"。

对话内容：
"""


class UserMemoryService:
    def __init__(self, repository: UserMemoryRepository | None = None):
        self.repo = repository or UserMemoryRepository()

    def get_memory_prompt(self) -> str:
        """将所有记忆格式化为 system prompt 片段，注入到消息列表前。"""
        memories = self.repo.list_all()
        if not memories:
            return ""
        lines = ["[关于用户，以下是已知的信息，请在对话中自然地参考：]"]
        for m in memories:
            lines.append(f"- {m.fact}")
        return "\n".join(lines)

    def list_all(self) -> list[dict]:
        return [{"id": m.id, "fact": m.fact, "created_at": m.created_at}
                for m in self.repo.list_all()]

    def delete(self, memory_id: int) -> bool:
        return self.repo.delete(memory_id)

    def clear(self) -> None:
        self.repo.clear_all()

    def extract_and_save(self, user_message: str, ai_reply: str, profile) -> list[str]:
        """从本轮对话中提取关于用户的新事实并保存。
        使用单独的 LLM 调用，不影响对话模型。
        返回新提取的事实列表。"""
        prompt = (
            f"{MEMORY_EXTRACTION_PROMPT}"
            f"用户：{user_message}\n"
            f"AI：{ai_reply[:500]}\n"
        )

        try:
            model = _build_extraction_model(profile)
            result = model.invoke(prompt)
            text = result.content if hasattr(result, "content") else str(result)
        except Exception:
            return []

        if not text or "NONE" in text.upper():
            return []

        saved = []
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # 去掉 markdown 列表前缀 "- " "* " "· "
            for prefix in ["- ", "· ", "* "]:
                if line.startswith(prefix):
                    line = line[len(prefix):]
                    break
            # 去掉数字序号 "1. " "1) "
            line = re.sub(r"^\d+[\.\)]\s*", "", line)
            line = line.strip()
            if line and len(line) > 2:
                result = self.repo.add_if_new(line)
                if result:
                    saved.append(line)
        return saved


def _build_extraction_model(profile):
    """为记忆提取创建低温 LLM 实例。"""
    common = {"model": profile.model, "temperature": 0.1}
    if profile.provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(**common, api_key=os.getenv(profile.api_key_env or ""),
                            base_url=profile.base_url or "https://api.deepseek.com",
                            timeout=profile.timeout_seconds, max_retries=profile.max_retries)
    elif profile.provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(**common, api_key=os.getenv(profile.api_key_env or ""),
                          base_url=profile.base_url or "https://api.openai.com/v1",
                          timeout=profile.timeout_seconds, max_retries=profile.max_retries)
    elif profile.provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(**common, base_url=profile.base_url or "http://127.0.0.1:11434")
    raise ValueError(f"不支持的 provider：{profile.provider}")
