# app/tools/ask_user.py — 向用户提问
# =============================================================================
# 当 LLM 需要用户做出选择或确认时调用。与 tool_confirm 不同，
# tool_confirm 是系统安全机制（确认危险操作），而 ask_user 是业务逻辑
# ——LLM 主动需要用户输入来继续任务。
# =============================================================================

import json
from langchain_core.tools import tool


@tool
def ask_user_question(questions_json: str) -> str:
    """向用户提问以获取决策信息。当你需要用户在多个方案之间选择、确认偏好、
    或提供你无法自行判断的信息时使用。

    Args:
        questions_json: JSON 数组，每个元素为:
            {
              "question": "问题文本",
              "header": "简短标签（≤12字）",
              "options": [{"label": "选项1", "description": "说明1"}, ...],
              "multiSelect": false
            }
            例如:
            [{"question":"使用哪种认证方式？","header":"认证方式",
              "options":[{"label":"JWT","description":"无状态令牌"},
                        {"label":"Session","description":"服务端会话"}],
              "multiSelect":false}]
    """
    # 此工具由 chat_service 拦截执行，不会走到这里
    # 如果在其他上下文调用，返回提示
    return "请等待用户回答..."
