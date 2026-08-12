# L8 — LangGraph StateGraph：用状态图控制程序流程
# 相比 L1~L7 的核心区别：
#
# ┌──────────┬──────────────────────────────────────┬──────────────────────────┐
# │  课程    │  核心机制                             │  谁做决策？               │
# ├──────────┼──────────────────────────────────────┼──────────────────────────┤
# │  L1      │  model.invoke("字符串")               │  无决策，单线执行          │
# │  L2      │  model.invoke([消息列表])              │  无决策，消息按顺序传入    │
# │  L3      │  prompt | model | parser（链）        │  无决策，数据从左到右流    │
# │  L4      │  chain.stream() + while True          │  无决策，循环 + 流式输出   │
# │  L5      │  create_agent(model, tools=[...])      │  LLM 决策：是否调工具？    │
# │  L6      │  FastMCP Server（暴露服务）             │  无决策，被动等待调用      │
# │  L7      │  MCP Client + Agent（桥接）            │  LLM 决策：是否调 MCP 工具 │
# │  L8 ←本课│  StateGraph（状态图）                  │  代码逻辑决策：走哪个分支？ │
# └──────────┴──────────────────────────────────────┴──────────────────────────┘
#
# L8 最大的转折：不调 LLM！用有向图（节点 + 边）控制程序流程。
#
# ── 四个关键区别 ──────────────────────────────────────────────────────────────
#
# 区别 1：不 import langchain，而是 import langgraph
#   L1~L5 的核心是 langchain_core / langchain_openai / langchain_deepseek
#   L6~L7 的核心是 mcp + langchain_mcp_adapters
#   L8 的核心是 langgraph —— 它不是 LLM 框架，而是 状态机 / 工作流 框架
#
# 区别 2：不调 LLM，而是"走节点"
#   L1~L4：每一步都必须调一次 model，等待 LLM 返回
#   L5/L7：由 LLM 决定是否调工具，Agent 负责循环
#   L8：   完全不需要 LLM！节点是普通 Python 函数，图负责按顺序/条件执行它们
#          图中的每个节点就是一个处理步骤，由代码逻辑决定下一步走哪
#
# 区别 3：控制流从"链式管道"变成"有向图"
#   L3/L4 的 Chain 是线性的：A → B → C，数据只能单向流动
#   L8 的 Graph 可以有分支、条件路由、循环：
#         START → read_question ──→ answer_python → END
#                              └─→ answer_general → END
#   数据存在共享的 state 字典中，每个节点读写同一个 state
#
# 区别 4：TypedDict 定义共享状态，替代 Chain 的隐式数据流
#   L3/L4 中数据通过 | 管道隐式传递，你不知道中间步骤拿到了什么
#   L8 中 LessonState(TypedDict) 明确定义了所有字段，每个节点声明输入/输出
#
# ── 架构对比 ──────────────────────────────────────────────────────────────────
#
#   L3/L4 Chain（线性管道）：
#   prompt ──→ model ──→ parser ──→ 结果
#   数据从左到右单向流动，无法分支
#
#   L8 StateGraph（有向图）：
#                    ┌─────────────────┐
#                    │  route_question │ ← 条件路由函数（纯 Python 逻辑）
#                    └──────┬──────┘
#                           │ return "python" 或 "general"
#              ┌────────────┼────────────┐
#              ▼            │            ▼
#   ┌──────────────┐        │   ┌──────────────┐
#   │ answer_python│        │   │answer_general│
#   └──────┬───────┘        │   └──────┬───────┘
#          │                │          │
#          ▼                │          ▼
#        END  ◄─────────────┘        END
#
#   节点 = 处理函数  边 = 流转方向  条件边 = if/else 分支
# =============================================================================
# 1. 导入依赖
# =============================================================================
# TypedDict：定义 state 的类型结构，每个字段的类型和可选性一目了然
from typing import TypedDict

# L8 新增：langgraph.graph — LangGraph 的图框架
# StateGraph：核心类，用节点 + 边构建有向图
# START：   图的入口标记（类似流程图的"开始"）
# END：     图的出口标记（类似流程图的"结束"）
from langgraph.graph import END, START, StateGraph


# =============================================================================
# 2. 定义共享状态 — TypedDict
# =============================================================================
# LessonState 是图中所有节点共享的数据结构。
# 每个节点读取 state 中的字段，处理后返回要更新的字段（部分更新）。
#
# 与 L1~L7 的对比：
#   L1~L2：无状态，每次 invoke 从头开始
#   L3~L4：历史记录在 history 列表中，但没有类型约束
#   L5/L7：messages 列表隐式承载状态
#   L8：   用 TypedDict 明确定义状态字段，IDE 有类型提示，不易出错
#
# total=False 的含义：
#   所有字段都是可选的（可选类型），节点可以只返回部分字段，
#   LangGraph 会自动合并（部分更新，而非整体替换）
class LessonState(TypedDict, total=False):
    question: str   # 用户输入的问题，由 read_question 填充
    answer: str     # 最终回答，由 answer_python 或 answer_general 填充


# =============================================================================
# 3. 定义节点函数 — 图中的处理步骤
# =============================================================================
# 每个节点是一个普通 Python 函数，接收整个 state 作为输入，返回要更新的字段。
#
# 与 L5/L6 的 tool 对比：
#   L5 @tool  / L6 @server.tool()：函数由 LLM 决定何时调用
#   L8 节点函数：函数由图的边（代码逻辑）决定何时执行，与 LLM 无关
#
# 返回值规则：
#   返回 dict，包含本次要更新的字段 → LangGraph 自动合并入 state
#   不返回的字段保持不变

def read_question(state: LessonState) -> dict:
    """读取并保留用户问题。"""
    print("正在执行：read_question")
    # 从 state 中读取 question，strip 去除首尾空格后写回
    return {"question": state["question"].strip()}


def answer_python(state: LessonState) -> dict:
    """回答 Python 相关问题。"""
    print("正在执行：answer_python")
    # 读取 state 中的 question，拼接回答后写回 answer 字段
    return {"answer": f"这是一个 Python 问题：{state['question']}"}


def answer_general(state: LessonState) -> dict:
    """回答其他类型的问题。"""
    print("正在执行：answer_general")
    return {"answer": f"这是一个普通问题：{state['question']}"}


# =============================================================================
# 4. 定义条件路由函数 — 图的"岔路口"
# =============================================================================
# 条件路由函数接收 state，返回一个字符串，决定走哪条边。
#
# 这是 L8 区别于 L1~L7 最关键的概念之一：
#   L1~L4：无分支，代码顺序执行
#   L5/L7：LLM 隐式分支（模型决定是否调工具），你在代码中看不到 if/else
#   L8：  显式分支，纯 Python if/else，逻辑完全可控、可调试
#
# 返回值必须是 add_conditional_edges 中映射表里存在的 key。
def route_question(state: LessonState) -> str:
    """根据问题内容选择下一个节点。"""
    # 纯 Python 逻辑判断，不依赖任何 LLM
    # 包含 "python" → 走 answer_python 节点
    # 其他内容     → 走 answer_general 节点
    if "python" in state["question"].lower():
        return "python"
    return "general"


# =============================================================================
# 5. 构建状态图 — 添加节点和边
# =============================================================================
# StateGraph(LessonState)：以 LessonState 为共享状态创建一个图构造器
builder = StateGraph(LessonState)

# add_node("名称", 函数)：向图中注册节点
# "名称" 是节点的唯一标识，边通过名称引用
builder.add_node("read_question", read_question)
builder.add_node("answer_python", answer_python)
builder.add_node("answer_general", answer_general)

# add_edge(起点, 终点)：固定边，无条件从起点走到终点
# START → read_question：图启动后第一个执行的节点
builder.add_edge(START, "read_question")

# add_conditional_edges(起点, 路由函数, 映射表)：条件边
# 从 read_question 出发，调用 route_question 得到返回值：
#   返回 "python"  → 走 answer_python 节点
#   返回 "general" → 走 answer_general 节点
#
# 与 L5/L7 的 Agent 对比：
#   Agent 的路由是 LLM 决定的 → 模型根据 tool_calls 自动选择
#   StateGraph 的路由是代码决定的 → route_question 中的 if/else 显式控制
builder.add_conditional_edges(
    "read_question",            # 从哪个节点出发
    route_question,             # 路由函数，读取 state 返回分支名
    {
        "python": "answer_python",    # 映射：route_question 返回 "python" → 去 answer_python
        "general": "answer_general",  # 映射：返回 "general" → 去 answer_general
    },
)

# 两个回答节点都通向 END：无论走哪个分支，执行完就结束
builder.add_edge("answer_python", END)
builder.add_edge("answer_general", END)


# =============================================================================
# 6. 编译图 — 从"蓝图"到"可执行引擎"
# =============================================================================
# compile() 验证图结构并创建可执行的 CompiledStateGraph 对象。
# 验证内容：所有边引用的节点都存在、没有孤立节点、没有死循环等。
#
# 与 L3/L4 Chain 的对比：
#   L3/L4：chain = prompt | model | parser → 编译后得到 Runnable 对象
#   L8：   graph = builder.compile()      → 编译后得到可执行的图引擎
#
#   两者都是"定义 → 编译 → 调用"的三段式，但 L8 的图可以有分支和循环
graph = builder.compile()

# =============================================================================
# 7. 调用图 — graph.invoke() 启动执行
# =============================================================================
# invoke() 接收初始 state（部分字段），按图的边自动走完所有节点。
#
# 执行流程（自动化的，无需手动控制）：
#   1. START → read_question（清洗问题，去掉首尾空格）
#   2. read_question 执行完 → 调用 route_question 判断
#   3. route_question 返回 "python" 或 "general"
#   4. 根据返回值执行 answer_python 或 answer_general
#   5. 回答节点执行完 → END
#
# 传入的 state 只需要包含当前已知的字段（question），
# answer 字段会在执行过程中由节点填充。
result = graph.invoke({"question": "  今天天气怎么样？  "})
print(result)

# 输出示例：
#   正在执行：read_question
#   正在执行：answer_general
#   {'question': '今天天气怎么样？', 'answer': '这是一个普通问题：今天天气怎么样？'}
#
# 如果改为 graph.invoke({"question": "  python 装饰器怎么用？  "})
#   正在执行：read_question
#   正在执行：answer_python
#   {'question': 'python 装饰器怎么用？', 'answer': '这是一个 Python 问题：python 装饰器怎么用？'}
#
# ── L8 小结 ──────────────────────────────────────────────────────────────────
#
# StateGraph 的三个核心概念：
#   1. State（状态）：TypedDict 定义，所有节点共享
#   2. Node（节点）：普通 Python 函数，接收 state 返回部分更新
#   3. Edge（边）：连线，决定下一个执行哪个节点
#      - 普通边：固定路线  A → B
#      - 条件边：分支路线  A → B 或 A → C，由路由函数决定
#
# 什么时候用 StateGraph 而不是 Chain？
#   - 需要条件分支（if/else 决定下一步做什么）→ StateGraph
#   - 需要循环（某步骤失败则重试）             → StateGraph
#   - 多个节点间共享同一份数据                  → StateGraph
#   - 简单线性流程（A → B → C 无分支）          → Chain 更简洁
#
# L8 为后面的多 Agent 编排（L9+）打下基础：
#   每个 Agent 就是一个节点，StateGraph 控制它们之间的协作流程。
