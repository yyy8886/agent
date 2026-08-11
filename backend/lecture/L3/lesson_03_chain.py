# L3 — 提示词模板 + Chain
# 相比 L2 的区别：不再手动拼消息列表再 model.invoke()，而是定义模板 → 用 | 串成链 → 一次 invoke。
# 本课独有：ChatPromptTemplate（{占位符}）、LCEL 管道（|）、StrOutputParser（自动提 .content）。
# =============================================================================
# 1. 导入依赖
# =============================================================================
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# L3 新增：Chain 的两大组件
# ChatPromptTemplate = 提示词模板，{占位符} 在运行时填入，结构与内容分离
# StrOutputParser    = 把 AIMessage 自动转成纯字符串，省去 .content
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from langchain_deepseek import ChatDeepSeek      # DeepSeek 官方集成
from langchain_ollama import ChatOllama          # 本地 Ollama
from langchain_openai import ChatOpenAI          # OpenAI 及兼容接口（含中转站）


# =============================================================================
# 2. 定位项目根目录，加载 .env 和 config.yaml
# =============================================================================
# __file__ = lecture/L3/lesson_03_chain.py → 上三级 = backend/
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
# 5. Chain：用管道 | 把 prompt → model → parser 串联起来
# =============================================================================
# L1/L2 的做法：手动拼消息 → model.invoke() → response.content
# L3 的做法：模板 + 模型 + 解析器 串成一条链，数据从左到右自动流转

# ChatPromptTemplate：定义提示词骨架，{占位符} 在 invoke 时填入
# 好处：提示词结构写一次，角色/风格/问题每次不同，可复用
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "你是一名{role}。使用{style}回答，先解释概念，再给一个简短例子。"),
        ("human", "{question}"),
    ]
)

# StrOutputParser：把 AIMessage 自动转成纯字符串，等价于每次手动 .content
parser = StrOutputParser()

# LCEL 管道语法 | ：数据从左向右流动
#   prompt  →  model  →  parser  →  最终纯文本字符串
#   填占位符    LLM调用   提取.content   拿到结果
chain = prompt | model | parser

question = input("你：").strip()
if not question:
    raise SystemExit("输入不能为空")

# chain.invoke({...})：传入字典，键对应模板中的 {占位符}
# LangChain 自动完成：填模板 → 调模型 → 解 content，一步到位
answer = chain.invoke(
    {
        "role": "Python 入门教师",   # 填入 {role}
        "style": "简体中文",         # 填入 {style}
        "question": question,        # 填入 {question}
    }
)

# answer 已经是纯字符串，无需再 .content
print(answer)
