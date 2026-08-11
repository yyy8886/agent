import os

import yaml
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_deepseek import ChatDeepSeek
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

import asyncio
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

# L7 完整流程：
# config.yaml 创建模型 -> MCP Client 发现 L6 工具 -> create_agent 组合模型和工具
# -> Agent 判断是否需要工具 -> 必要时通过 MCP 调用工具 -> 输出最终回答

# =============================================================================
# 1. 读取模型配置
# =============================================================================
# __file__ = lecture/L7/lesson_07_mcp_client.py，向上三级得到 backend 目录。
backend_dir = Path(__file__).resolve().parent.parent.parent

# .env 保存 API Key，config.yaml 决定当前使用哪个模型。
load_dotenv(backend_dir / ".env")

config_path = backend_dir / "config.yaml"
with config_path.open("r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

active_model = config["app"]["active_model"]
model_config = config["models"][active_model]

# =============================================================================
# 2. 根据 provider 准备 API Key 和服务地址
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
# 3. 创建 config.yaml 当前选中的聊天模型
# =============================================================================
# 这一部分仍是 L1 学过的模型切换方式，与 MCP 无关。
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


async def main() -> None:
    # 第 4 步：计算 L6 MCP Server 文件的路径。
    # __file__ 是当前 L7 文件，parent.parent 回到 lecture 目录。
    server_file = Path(__file__).parent.parent / "L6" / "mcp_server.py"

    # 第 5 步：创建 MCP Client，并告诉它如何启动 Server。
    # sys.executable 是当前虚拟环境的 Python；stdio 是双方的通信方式。
    client = MultiServerMCPClient(
        {
            "lesson-tools": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(server_file)],
            }
        }
    )

    # 第 6 步：连接 MCP Server 并发现工具。
    # get_tools() 内部会启动 L6 Server、完成初始化握手，
    # 再发送 tools/list 请求，最后把发现的 MCP 工具转换成 LangChain 工具。
    # 此时只是获取工具列表，还没有执行 get_current_time。
    tools = await client.get_tools()

    # 第 7 步：查看 Client 从 Server 中发现了哪些工具。
    print("发现的工具数量：", len(tools))

    for tool in tools:
        print("工具名称：", tool.name)
        print("工具说明：", tool.description)

    # 第 8 步：把聊天模型和 MCP 工具组合成 Agent。
    # create_agent 会负责“模型决策 -> 调用工具 -> 模型总结”的自动循环。
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=(
            "你是一名简洁的中文助手。"
            "用户询问当前时间时，必须调用 get_current_time 工具，不能猜测。"
        ),
    )

    # 第 9 步：读取本次用户问题。
    # 时间问题需要 MCP 工具，普通知识问题可以由模型直接回答。
    question = input("你：").strip()

    if not question:
        raise SystemExit("输入不能为空")

    # 第 10 步：异步运行 Agent。
    # Agent 先让模型判断是否需要工具；如果需要，它会通过 MCP 执行工具，
    # 再把工具结果交给模型，由模型组织最终回答。
    result = await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": question,
                }
            ]
        }
    )

    # 第 11 步：messages 包含用户消息、模型决策、工具结果和最终回答。
    # 列表最后一项就是应该展示给用户的 AIMessage。
    final_message = result["messages"][-1]
    print("Agent 最终回答：", final_message.content)


if __name__ == "__main__":
    # 从普通 Python 程序进入异步 main() 函数。
    asyncio.run(main())
