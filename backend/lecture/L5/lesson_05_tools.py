# L5 — Agent 与工具调用
# 相比 L4 的区别：
#   1. @tool 装饰器 → 把普通 Python 函数变成模型可调用的"工具"
#   2. create_agent() → 一行创建 Agent，它内部自动完成"决策→调用→总结"循环
#   3. 模型不再是纯聊天，而是能调用函数获取实时数据（时间、天气、数据库等）
#   4. Agent 返回 messages 列表，最后一条就是最终回答
# =============================================================================
# 1. 导入依赖
# =============================================================================
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# L5 新增：datetime — 获取系统时间，get_current_time 工具的实际数据来源
from datetime import datetime

# L5 新增：@tool — LangChain 的工具装饰器
# 往一个普通函数上加 @tool，LangChain 会自动提取函数名、docstring 作为工具描述、
# 参数类型作为 schema，模型就能理解"有这个工具可以用，参数是什么"
from langchain_core.tools import tool

# 前几课学过的消息类型和 Chain 组件
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser

from langchain_deepseek import ChatDeepSeek      # DeepSeek 官方集成
from langchain_ollama import ChatOllama          # 本地 Ollama
from langchain_openai import ChatOpenAI          # OpenAI 及兼容接口（含中转站）

# L5 新增：create_agent — LangChain 的高层 Agent 构造函数
# 以前需要手动：bind_tools → invoke → 检查 tool_calls → 执行工具 → 再 invoke
# create_agent 把这些步骤打包成一个对象，内部自动处理整个循环
from langchain.agents import create_agent


# =============================================================================
# 2. 定义工具：用 @tool 把普通函数变成模型可调用的工具
# =============================================================================
# @tool 装饰器做了什么：
#   1. 读取函数名 → 工具名 "get_current_time"
#   2. 读取 docstring → 工具描述，模型据此判断"什么时候该用这个工具"
#   3. 读取参数类型 → 生成 JSON Schema，API 用这个 schema 来规范调用
#
# 关键：docstring 必须写清楚工具的功能，因为模型就是靠这段文字来决定是否调用它。
# 不写 docstring = 模型不知道这个工具能干嘛 = 永远不会调用。
@tool
def get_current_time() -> str:
    """返回当前电脑所在时区的日期、时间和时区名称。"""
    now = datetime.now().astimezone()       # 获取本地时区的当前时间
    return now.isoformat(timespec="seconds") # 格式：2026-08-11T15:30:00+08:00


# =============================================================================
# 3. 定位项目根目录，加载 .env 和 config.yaml
# =============================================================================
# __file__ = lecture/L5/lesson_05_tools.py → 上三级 = backend/
backend_dir = Path(__file__).resolve().parent.parent.parent

load_dotenv(backend_dir / ".env")

config_path = backend_dir / "config.yaml"
with config_path.open("r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

active_model = config["app"]["active_model"]
model_config = config["models"][active_model]


# =============================================================================
# 4. 根据 provider 获取 API Key 和 base_url
# =============================================================================
provider = model_config["provider"]  # deepseek | openai | ollama

PROVIDER_ENV_MAP = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai":   "OPENAI_API_KEY",
    "ollama":   None,                # Ollama 本地运行，无需 Key
}
PROVIDER_DEFAULT_BASE_URL = {
    "deepseek": "https://api.deepseek.com",
    "openai":   "https://api.openai.com/v1",
    "ollama":   "http://127.0.0.1:11434",
}

env_var = PROVIDER_ENV_MAP.get(provider)
if env_var:
    api_key = os.getenv(env_var)
    if not api_key:
        raise RuntimeError(f"未找到 {env_var}，请检查 backend/.env")
else:
    api_key = "not-needed"

base_url = model_config.get("base_url") or PROVIDER_DEFAULT_BASE_URL.get(provider, "")


# =============================================================================
# 5. 创建模型实例
# =============================================================================
common_kwargs = {
    "model": model_config["model"],
    "temperature": model_config["temperature"],
}

if provider == "deepseek":
    model = ChatDeepSeek(
        **common_kwargs,
        api_key=api_key,
        base_url=base_url,
        timeout=model_config.get("timeout_seconds", 60),
        max_retries=model_config.get("max_retries", 2),
    )
elif provider == "openai":
    model = ChatOpenAI(
        **common_kwargs,
        api_key=api_key,
        base_url=base_url,
        timeout=model_config.get("timeout_seconds", 60),
        max_retries=model_config.get("max_retries", 2),
    )
elif provider == "ollama":
    model = ChatOllama(
        **common_kwargs,
        base_url=base_url,
    )
else:
    raise RuntimeError(f"不支持的 provider: {provider}")


# =============================================================================
# 6. 创建 Agent：把模型 + 工具 + 系统提示打包成一个智能体
# =============================================================================
# create_agent 内部做了什么（自动化的"决策→执行→总结"循环）：
#
#   用户消息 "现在几点？"
#     → 第 1 次 invoke：模型读取 system_prompt + 用户消息 + 可用工具列表
#                       模型决定："我需要调 get_current_time"
#                       返回 AIMessage（包含 tool_calls）
#     → Agent 自动执行 get_current_time()，拿到真实时间字符串
#     → 第 2 次 invoke：模型读取用户消息 + tool_calls 记录 + 工具结果
#                       模型组织自然语言："现在是 2026 年 8 月 11 日 15:30 CST"
#                       返回 AIMessage（纯文本）
#
# 对比 L4：L4 是手动写 for 循环处理 tool_calls，create_agent 帮你自动化了这个循环
agent = create_agent(
    model=model,                            # 底层 LLM，负责决策和总结
    tools=[get_current_time],               # 可用工具列表，这里只有一个时间工具
    system_prompt=(                         # 系统提示：告诉 Agent 的行为规则
        "你是一名简洁的中文助手。"
        "涉及当前时间时必须调用工具，不得猜测。"  # 强制调用工具，防止模型瞎编
    ),
)


# =============================================================================
# 7. 调用 Agent 并获取结果
# =============================================================================
# agent.invoke() 接收一个 message 列表，格式是 [{"role": "user", "content": "..."}]
# 返回一个字典，其中 result["messages"] 是完整的消息历史（包含内部轮次）
result = agent.invoke(
    {
        "messages": [
            {
                "role": "user",            # 用户角色
                "content": "现在几点？",    # 问题内容
            }
        ]
    }
)

# result["messages"] 里有什么（按顺序）：
#   messages[0]  = HumanMessage("现在几点？")      ← 用户输入
#   messages[1]  = AIMessage(tool_calls=[...])      ← 模型决定调工具（内部轮次）
#   messages[2]  = ToolMessage("2026-08-11T15:30:00") ← 工具执行结果（内部轮次）
#   messages[-1] = AIMessage("现在是...")            ← 最终自然语言回复 ✅

# 拿最后一条消息，就是用户最终看到的回答
final_message = result["messages"][-1]
print(final_message.content)
