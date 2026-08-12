"""L9 进阶练习：LangGraph Agent 调用 MCP 工具。"""

import os

import yaml
from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

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

    # 第 8 步：把 MCP 工具的名称、说明和参数 schema 告诉模型。
    # bind_tools() 只绑定工具描述，不会立刻执行工具。
    model_with_tools = model.bind_tools(tools)

    async def call_model(state: MessagesState) -> dict:
        """调用模型，并把模型返回的 AIMessage 追加到消息 State。"""
        # 系统提示约束工具边界，避免模型为普通知识问题调用时间工具。
        messages = [
            SystemMessage(
                content=(
                    "你是一名简洁的中文助手。"
                    "只有当用户询问当前日期、当前时间或当前时区时，"
                    "才调用 get_current_time；其他问题直接回答，不得调用该工具。"
                )
            ),
            *state["messages"],
        ]
        response = await model_with_tools.ainvoke(messages)
        return {"messages": [response]}

    # 第 9 步：创建工具节点。
    # ToolNode 会读取 AIMessage 中的 tool_calls，并执行对应的 MCP 工具。
    tool_node = ToolNode(tools)

    # 第 10 步：手动画出 Agent 的决策循环。
    builder = StateGraph(MessagesState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", tool_node)

    # 用户消息先进入模型节点。
    builder.add_edge(START, "agent")

    # tools_condition 检查模型最后一条消息：
    # 有 tool_calls -> 返回 "tools"；没有 tool_calls -> 返回 END。
    builder.add_conditional_edges("agent", tools_condition)

    # 工具执行完成后，必须回到模型，让模型读取 ToolMessage 并总结。
    builder.add_edge("tools", "agent")

    # 第 11 步：加入内存 Checkpointer，让本次图运行按 thread_id 保存状态。
    checkpointer = InMemorySaver()
    graph = builder.compile(checkpointer=checkpointer)

    # 第 12 步：读取问题并运行图。
    question = input("你：").strip()
    if not question:
        raise SystemExit("输入不能为空")

    config = {
        "configurable": {
            "thread_id": "mcp-agent-thread",
        }
    }

    result = await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": question,
                }
            ]
        },
        config=config,
    )

    # 第 13 步：查看消息循环，并打印最后一条 AIMessage。
    for index, message in enumerate(result["messages"]):
        print(index, type(message).__name__, message.content)

    final_message = result["messages"][-1]
    print("Agent 最终回答：", final_message.content)


if __name__ == "__main__":
    # 从普通 Python 程序进入异步 main() 函数。
    asyncio.run(main())
