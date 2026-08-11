# L2 — 多轮对话上下文
# 相比 L1 的区别：不再是 model.invoke("字符串")，而是 model.invoke([消息列表])。
# 本课独有：SystemMessage（设角色）+ HumanMessage（用户）+ AIMessage（AI 历史）组成数组传入。
# 模型能"看到"之前说了什么，因此可以追问上一轮的内容。
# =============================================================================
# 1. 导入依赖
# =============================================================================
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# L2 新增：三种消息类型，用来构造多轮对话上下文
# SystemMessage = 系统指令（设定 AI 的角色、语气、规则）
# HumanMessage  = 用户说的内容
# AIMessage     = AI 之前的回复（用于让模型"记住"自己说过什么）
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from langchain_deepseek import ChatDeepSeek      # DeepSeek 官方集成
from langchain_ollama import ChatOllama          # 本地 Ollama
from langchain_openai import ChatOpenAI          # OpenAI 及兼容接口（含中转站）


# =============================================================================
# 2. 定位项目根目录，加载 .env 和 config.yaml
# =============================================================================
# __file__ = lecture/L2/lesson_02_messages.py → 上三级 = backend/
backend_dir = Path(__file__).resolve().parent.parent.parent

load_dotenv(backend_dir / ".env")

config_path = backend_dir / "config.yaml"
with config_path.open("r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

active_model = config["app"]["active_model"]
model_config = config["models"][active_model]


# =============================================================================
# 3. 根据 provider 获取 API Key 和 base_url
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
# 4. 创建模型实例
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
# 5. 多轮对话：用消息列表传递上下文
# =============================================================================
# L1 中 model.invoke("你好") 只传了一个字符串，模型不知道之前聊过什么。
# L2 的核心变化：invoke() 接收一个消息列表，按顺序排列，模型会"看到"所有历史。

messages = [
    # SystemMessage：设定 AI 的角色，优先级最高但用户不可见
    SystemMessage(
        content="你是一名简洁的中文助手。"
    ),
    # HumanMessage：第一轮用户说的话
    HumanMessage(
        content="请给我起一个昵称。"
    ),
    # AIMessage：第一轮 AI 的回复（手动填的"假历史"，模拟之前的对话）
    AIMessage(
        content="以后我就叫你小火箭吧。"
    ),
    # HumanMessage：第二轮用户的问题——引用了上一轮的内容
    HumanMessage(
        content="你刚才给我起的昵称是什么？"
    ),
]

# 模型会依次读完 messages，然后生成对最后一条 HumanMessage 的回复
response = model.invoke(messages)
print(f"{provider}：{response.content}")
