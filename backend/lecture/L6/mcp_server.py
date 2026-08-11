# L6 — MCP Server：把工具暴露为服务
# 相比 L1~L5 的核心区别：
#
# ┌──────────┬──────────────────────────────────┬──────────────────────────────────┐
# │  课程    │  调 LLM 的方式                    │  工具/能力的形态                  │
# ├──────────┼──────────────────────────────────┼──────────────────────────────────┤
# │  L1      │  model.invoke("字符串")           │  无工具，纯文本问答                │
# │  L2      │  model.invoke([消息列表])          │  无工具，手动拼 System/Human/AI   │
# │  L3      │  chain = prompt | model | parser  │  无工具，ChatPromptTemplate 模板化 │
# │  L4      │  chain.stream() + while True      │  无工具，MessagesPlaceholder 记历史 │
# │  L5      │  create_agent(model, tools=[...])  │  @tool 装饰器，Agent 内嵌调用       │
# │  L6 ←本课│  不调 LLM！只暴露服务              │  MCP 协议：Tool/Resource/Prompt    │
# └──────────┴──────────────────────────────────┴──────────────────────────────────┘
#
# L6 最大的转折：不是"调用 LLM 的客户端"，而是"被 LLM 调用的服务端"。
#
# ── 三个关键区别 ──────────────────────────────────────────────────────────────
#
# 区别 1：不再 import langchain，而是 import mcp
#   L1~L5 全部依赖 LangChain（langchain_core / langchain_openai / langchain_deepseek）
#   L6 用的是 FastMCP（mcp.server.fastmcp），它是 MCP 协议的 Python 服务端框架。
#   这意味着本文件与任何 LLM SDK 解耦 —— 它是一个纯服务端，任何 MCP 客户端都能连。
#
# 区别 2：不是"我调模型"，而是"模型调我"
#   L1~L4：app 主动 invoke 模型，等待模型返回文本。
#   L5：  Agent 把工具挂在内部，模型有 tool_calls 时 Agent 代为执行。
#   L6：  工具不在 Agent 进程内，而是独立进程，通过 stdio 暴露给外部 MCP 客户端。
#         客户端（如 Claude Desktop、VS Code 插件、L7 中自己写的 MCP 客户端）
#         连接到本服务后，能用 Tool / Resource / Prompt 这三种能力。
#
# 区别 3：Tool / Resource / Prompt 是 MCP 的三种原语，与 LangChain 无关
#   @server.tool()    → 可被模型调用的函数（类似 L5 的 @tool，但暴露为网络服务）
#   @server.resource()→ 只读数据，模型可以直接读取而不需要"调用"（L1~L5 无此概念）
#   @server.prompt()  → 可复用的消息模板（类似 L3 的 ChatPromptTemplate，但暴露为服务）
#
# ── 架构对比 ──────────────────────────────────────────────────────────────────
#
#   L5 架构（Agent 内嵌工具）：
#   ┌─────────────┐
#   │  用户 → Agent │
#   │  Agent 内有:  │
#   │   model       │
#   │   @tool       │  ← 工具在同一个进程里
#   └─────────────┘
#
#   L6 架构（MCP Server 独立服务）：
#   ┌──────────────┐   stdio   ┌───────────────┐
#   │  MCP 客户端    │◄────────►│  MCP Server    │
#   │  (Claude等)   │          │  本文件         │
#   │               │          │  @tool         │  ← 工具在独立进程
#   │               │          │  @resource     │
#   │               │          │  @prompt       │
#   └──────────────┘          └───────────────┘
#
#   好处：工具与 LLM 解耦 → 一个 MCP Server 可被多个不同客户端复用
#         可以用任何语言写工具 → 不限于 Python/LangChain
# =============================================================================
# 1. 导入依赖
# =============================================================================
# L6 只用了标准库 datetime + mcp 包，完全没有 langchain 的影子
from datetime import datetime

# FastMCP：MCP Server 的快速构建框架
# 功能类似 Flask/FastAPI 但面向 MCP 协议而非 HTTP
# 自动处理 JSON-RPC 通信、工具注册、资源暴露、提示词模板
from mcp.server.fastmcp import FastMCP


# =============================================================================
# 2. 创建 MCP Server 实例
# =============================================================================
# FastMCP 是本课的核心类，替代了 L1~L5 中所有的 LangChain 组件：
#   L1~L5 创建的是 model / chain / agent / parser
#   L6  创建的是 server —— 一个等待客户端连接的服务进程
server = FastMCP(
    name="lesson-tools",                                    # 服务名称，客户端列表中显示
    instructions="提供 L6 课程中的低风险本地工具。",          # 使用说明，告诉客户端这个服务能干嘛
)


# =============================================================================
# 3. 定义 Prompt — MCP 三大原语之一
# =============================================================================
# @server.prompt()：暴露可复用的消息模板。
#
# 与 L3 ChatPromptTemplate 的异同：
#   相同：都是"参数化的提示词模板"，调用时填入变量，得到完整消息
#   不同：L3 的模板在 LangChain 进程内用；L6 的模板暴露给远程客户端，
#         客户端可以先取模板，在自己的 LLM 调用中使用
#
# 客户端调用方式（MCP 协议）：
#   客户端发送 prompts/get 请求，参数 {name: "python_teacher", arguments: {topic: "装饰器"}}
#   服务端返回一个完整消息（含角色和内容），客户端直接用它调 LLM
@server.prompt(
    name="python_teacher",                                  # 提示词名称，客户端通过这个名字引用
    description="生成一个用于讲解 Python 主题的用户提示词。", # 描述，客户端 UI 中显示
)
def python_teacher(topic: str) -> str:
    """根据主题生成教学提示词。"""
    return (
        f"请使用简体中文讲解 Python 的 {topic}。"            # topic 是参数，运行时由客户端传入
        "先解释概念，再给一个简短例子，最后列出一个常见错误。"
    )


# =============================================================================
# 4. 定义 Resource — MCP 三大原语之二
# =============================================================================
# @server.resource()：暴露只读数据端点。
#
# Resource 是 L1~L5 完全没有的概念！
# Tool 是"做事情"（执行动作），Resource 是"读资料"（获取内容）。
# 模型可以像"打开文件"一样读取 Resource，而不需要调用一个函数。
#
# 典型场景：知识库、文档、配置、课程大纲等静态或准静态内容。
# 客户端可以通过 URI（lesson://overview）读取内容，就像访问网页。
@server.resource(
    "lesson://overview",                                    # URI：唯一标识这个资源（类似网页地址）
    name="l6_overview",                                     # 资源名称，客户端 UI 中显示
    description="L6 课程的只读简介。",                        # 描述
    mime_type="text/plain",                                 # MIME 类型，客户端据此决定如何展示
)
def get_l6_overview() -> str:
    """返回 L6 课程简介。"""
    return (
        "L6 学习 MCP Server：Tool 用于执行动作，"
        "Resource 用于读取内容，Prompt 用于生成消息模板。"
    )


# =============================================================================
# 5. 定义 Tool — MCP 三大原语之三
# =============================================================================
# @server.tool()：暴露可被模型调用的函数。
#
# 与 L5 @tool 的异同：
#   相同：都是把 Python 函数变成模型可调用的工具
#         docstring 都是工具描述，模型据此判断何时调用
#         返回的字符串都会回传给模型作为工具执行结果
#   不同：L5 的 @tool 在 create_agent() 内部使用，与 Agent 同进程
#         L6 的 @server.tool() 通过 stdio 暴露，任何 MCP 客户端都能远程调用
#
# 执行流程（由 MCP 客户端驱动）：
#   1. 客户端调用 tools/list → 发现 get_current_time 可用
#   2. 用户说"现在几点" → LLM 决定调 get_current_time
#   3. 客户端调用 tools/call {name: "get_current_time", arguments: {}}
#   4. 本函数执行，返回时间字符串
#   5. 客户端把结果回传给 LLM，LLM 组织成自然语言回答
@server.tool()
def get_current_time() -> str:
    """返回当前电脑所在时区的日期、时间和时区偏移。"""
    now = datetime.now().astimezone()
    return now.isoformat(timespec="seconds")


# =============================================================================
# 6. 启动 MCP Server — stdio 传输方式
# =============================================================================
# server.run(transport="stdio") 的含义：
#   服务端通过标准输入/输出（stdin/stdout）与客户端通信
#   客户端启动本进程后，往 stdin 写 JSON-RPC 请求，从 stdout 读响应
#
# 与 L5 的区别：
#   L5：agent.invoke({"messages": [...]}) → 程序主动发起调用，拿到结果后结束
#   L6：server.run() → 程序阻塞等待客户端连接，一直运行直到客户端断开
#
# 两种传输方式：
#   stdio：  客户端直接 spawn 本进程，通过管道通信（本课用的方式）
#   sse/http：服务端作为独立 HTTP 服务运行，客户端通过 HTTP 连接（更解耦）
if __name__ == "__main__":
    server.run(transport="stdio")
