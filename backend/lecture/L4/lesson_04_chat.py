# L4 — 流式输出 + 真正的多轮对话
# 相比 L3 的区别：
#   1. chain.stream() 替代 chain.invoke() → 逐字"打字"而非一次性返回
#   2. MessagesPlaceholder("history") → 模板中开一个槽，运行时塞入历史消息
#   3. while True 循环 → 不再是单次问答，可以一直聊下去
#   4. history.append() → 每轮结束后记录本轮 Q&A，下一轮自动带上
# =============================================================================
# 1. 导入依赖
# =============================================================================
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# L2 学的：HumanMessage + AIMessage，构造单条对话
# L3 学的：ChatPromptTemplate + StrOutputParser，链式调用
# L4 新增：MessagesPlaceholder — 模板中一个"可变插槽"，运行时把整个 history 列表塞进去
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser

from langchain_deepseek import ChatDeepSeek      # DeepSeek 官方集成
from langchain_ollama import ChatOllama          # 本地 Ollama
from langchain_openai import ChatOpenAI          # OpenAI 及兼容接口（含中转站）


# =============================================================================
# 2. 定位项目根目录，加载 .env 和 config.yaml
# =============================================================================
# __file__ = lecture/L4/lesson_04_chat.py → 上三级 = backend/
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
# 5. 搭建 Chain：模板含历史插槽 + 模型 + 解析器
# =============================================================================
# MessagesPlaceholder("history") 是 L4 区别于 L3 的关键：
# L3 模板只有固定占位符 {role} {question}，每次调用互不相关
# L4 模板多了一个 "history" 槽，每次把完整的聊天记录列表塞进去，模型就有了"记忆"
prompt = ChatPromptTemplate.from_messages(
    [
        # system 消息：固定角色设定，所有轮次共享
        ("system", "你是一名耐心的 Python 入门教师。使用简体中文，回答清晰但不过度冗长。"),
        # MessagesPlaceholder：可变插槽，运行时把 history 消息列表全部插入此处
        MessagesPlaceholder("history"),
        # human 消息：当前这一轮的提问
        ("human", "{question}"),
    ]
)

parser = StrOutputParser()

# 链：模板 → 模型 → 解析器（数据流向和 L3 一致，只是多了 history 插槽）
chain = prompt | model | parser


# =============================================================================
# 6. 多轮对话循环：while True + 流式输出 + 历史记录
# =============================================================================
# history 列表：从头到尾记录所有 HumanMessage 和 AIMessage
# 第一轮为空 → 第二轮有 2 条 → 第三轮有 4 条 → 越来越长
history = []

print("输入 exit 或 quit 结束对话。")

while True:
    question = input("你：").strip()

    # 退出条件
    if question.lower() in {"exit", "quit"}:
        print("对话结束。")
        break

    if not question:
        print("输入不能为空。")
        continue

    # 打印 provider 前缀，end="" 不换行，flush=True 立即显示
    print(f"{provider}：", end="", flush=True)

    parts = []  # 收集流式碎片，最后拼成完整回答

    # chain.stream()：L4 的核心 — 替代 chain.invoke()
    # invoke() 等全部生成完才返回；stream() 生成一个 token 就 yield 一个
    # 传入的 history 是当前所有历史消息，模型因此"记得"之前聊过什么
    for chunk in chain.stream(
        {
            "history": history,     # 填入 MessagesPlaceholder("history") 的槽
            "question": question,   # 填入 {question} 占位符
        }
    ):
        # 立即打印每个碎片，end="" 不换行，flush=True 确保逐字显示
        print(chunk, end="", flush=True)
        parts.append(str(chunk))    # 同时收集到列表，后面拼完整字符串

    print()                          # 流式结束，补一个换行
    answer = "".join(parts)          # 把 ["你", "好", "，", "世界"] 拼成 "你好，世界"

    # 将本轮 Q&A 追加到 history，下一轮循环自动带入
    # 这就是"记忆"的来源 — 不是魔法，就是每次把越来越长的消息列表传进去
    history.append(HumanMessage(content=question))   # 本轮用户说的
    history.append(AIMessage(content=answer))        # 本轮 AI 回的
