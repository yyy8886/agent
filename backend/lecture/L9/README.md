# L9 LangGraph：循环与 Checkpointer

L8 学习了固定边和条件边：

```text
START -> read_question -> 条件判断 -> 某一个回答节点 -> END
```

这些流程只向前执行一次。复杂 Agent 经常需要重复某个步骤，例如：

- 工具调用失败后重试。
- 检查回答，不合格就重新生成。
- 逐步执行任务，直到满足停止条件。

L9 学习两个能力：

1. **循环**：让条件边返回之前的节点。
2. **Checkpointer**：按照 `thread_id` 保存每次运行的 State。

本课继续使用普通 Python 函数，不接模型和 MCP。先看懂流程控制，再加入昂贵且不稳定的外部调用。

## 本课最终流程

第一部分先完成一个计数循环：

```text
START
  ↓
increase_count
  ↓
count < 3 ?
  ├─ 是 -> 回到 increase_count
  └─ 否 -> END
```

第二部分加入 Checkpointer：

```text
thread_id = "lesson-thread"
  -> 保存该线程每一步的 State
  -> 稍后读取该线程的最新 State
```

## 为什么循环必须有停止条件

下面这种图会一直运行：

```text
node -> node -> node -> ...
```

生产中的循环至少需要一种限制：

- 最大次数。
- 超时时间。
- 明确的成功或失败状态。
- 人工终止或取消。

本课使用 `count >= 3` 作为停止条件。后续工具重试也必须保留最大次数。

## 检查点 1：创建课程文件

在 `backend` 目录运行：

```powershell
New-Item lecture\L9 -ItemType Directory -Force
New-Item lecture\L9\lesson_09_loop.py -ItemType File
```

## 检查点 2：定义循环 State 和节点

在 `lesson_09_loop.py` 中写入：

```python
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class LoopState(TypedDict):
    count: int


def increase_count(state: LoopState) -> dict:
    """把计数增加 1。"""
    new_count = state["count"] + 1
    print(f"正在执行 increase_count：{new_count}")
    return {"count": new_count}
```

这里节点返回新的 `count`，LangGraph 将它合并到 State。

## 检查点 3：定义继续或结束的路由

继续加入：

```python
def route_after_count(state: LoopState) -> str:
    """计数未达到 3 时继续，否则结束。"""
    if state["count"] < 3:
        return "continue"
    return "stop"
```

路由标签含义：

```text
continue -> 再执行一次 increase_count
stop     -> 进入 END
```

路由函数只读取 State，不更新 State。

## 检查点 4：构建循环图

继续加入：

```python
builder = StateGraph(LoopState)
builder.add_node("increase_count", increase_count)

builder.add_edge(START, "increase_count")
builder.add_conditional_edges(
    "increase_count",
    route_after_count,
    {
        "continue": "increase_count",
        "stop": END,
    },
)

graph = builder.compile()

result = graph.invoke({"count": 0})
print("最终 State：", result)
```

关键是：

```python
"continue": "increase_count"
```

条件边重新指向已经执行过的节点，因此形成循环。

运行：

```powershell
python -m py_compile lecture\L9\lesson_09_loop.py
python lecture\L9\lesson_09_loop.py
```

预期输出：

```text
正在执行 increase_count：1
正在执行 increase_count：2
正在执行 increase_count：3
最终 State： {'count': 3}
```

## 循环是怎样停止的

```text
初始 count = 0
  -> 节点更新为 1 -> continue
  -> 节点更新为 2 -> continue
  -> 节点更新为 3 -> stop
  -> END
```

路由判断发生在节点更新 State 之后，所以它看到的是新值。

## 检查点 5：加入 InMemorySaver

循环验证完成后，在导入区增加：

```python
from langgraph.checkpoint.memory import InMemorySaver
```

把：

```python
graph = builder.compile()
```

改为：

```python
checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)
```

使用 Checkpointer 后，每次调用都必须提供 `thread_id`：

```python
config = {
    "configurable": {
        "thread_id": "lesson-thread",
    }
}

result = graph.invoke(
    {"count": 0},
    config=config,
)
print("最终 State：", result)
```

### thread_id 是什么

`thread_id` 是一条流程或会话的标识：

```text
thread-a -> 保存 thread-a 的 State
thread-b -> 保存 thread-b 的 State
```

它不是 Python 线程，也不是操作系统进程 ID。它更接近“会话编号”。

同一个 `thread_id` 会让 Checkpointer 找到同一条流程的历史；不同 `thread_id` 的 State 相互隔离。

## 检查点 6：读取保存的 State

图运行后加入：

```python
snapshot = graph.get_state(config)
print("保存的 State：", snapshot.values)
print("下一节点：", snapshot.next)
```

运行完成后，预期类似：

```text
保存的 State： {'count': 3}
下一节点： ()
```

`next` 是空元组，说明图已经到达 `END`，没有待执行节点。

## InMemorySaver 的边界

`InMemorySaver` 只把检查点保存在当前 Python 进程的内存里：

- 程序运行期间可以读取。
- 程序退出后数据消失。
- 不适合作为最终桌宠的持久化存储。

它适合教学和测试。后续桌宠会使用可持久化方案，并结合 SQLite 保存用户会话。

## Checkpointer 与普通 State 的区别

```text
State：当前流程正在传递的数据
Checkpointer：按 thread_id 保存 State 的历史快照
```

只定义 State 不代表程序重启后会自动记住它。是否保存、保存到哪里，由 Checkpointer 决定。

## 常见错误

### `Checkpointer requires ... thread_id`

编译时加入了 Checkpointer，但调用时没有提供 `thread_id`。使用：

```python
config = {"configurable": {"thread_id": "lesson-thread"}}
graph.invoke({"count": 0}, config=config)
```

### 无限循环或递归限制错误

通常说明路由永远返回 `continue`，或者停止条件写错。检查：

```python
if state["count"] < 3:
```

不要依赖 LangGraph 的递归限制代替自己的业务停止条件。

### 把 thread_id 当成用户 ID

一个用户可以有多条会话，因此 `thread_id` 通常代表会话或任务，不应直接等同于用户 ID。

## L9 验收目标

- [ ] 能画出循环返回边。
- [ ] 能解释为什么循环必须有最大次数或停止条件。
- [ ] 能让 `count` 从 0 循环到 3。
- [ ] 能使用 `InMemorySaver` 编译图。
- [ ] 能解释 `thread_id` 是会话标识，不是系统线程。
- [ ] 能通过 `graph.get_state(config)` 读取最终 State。
- [ ] 能说明 InMemorySaver 在程序退出后不会保留数据。

完成这些基础后，再把循环替换成真实 Agent 场景，例如“模型决定调用工具，工具完成后回到模型”。

## 进阶实践：真实 Agent 图调用 MCP

计数循环已经证明“条件边可以返回旧节点”。现在把它映射为真实 Agent：

```text
START
  ↓
agent（模型节点）
  ↓
模型是否提出 tool_calls？
  ├─ 否 -> END
  └─ 是 -> tools（MCP 工具节点）
              ↓
          回到 agent
```

假设用户问“现在几点”：

```text
第 1 次 agent：模型不知道实时信息，提出 get_current_time tool_call
  -> tools：通过 MCP 调用 L6 Server，得到当前时间
  -> 回到 agent
第 2 次 agent：模型读取工具结果，生成最终中文回答
  -> 没有新的 tool_calls
  -> END
```

这就是 L5/L7 中 `create_agent()` 内部循环的图形化版本。本节不使用 `create_agent()`，因为我们要亲手控制节点和边。

### 三个新组件

```python
from langgraph.graph import MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
```

- `MessagesState`：内置的消息 State，包含 `messages` 列表，并按顺序追加消息。
- `ToolNode`：读取最后一条 AIMessage 的 `tool_calls`，执行对应 LangChain 工具，并追加 ToolMessage。
- `tools_condition`：检查最后一条 AIMessage；有工具请求返回 `"tools"`，没有则返回 `END`。

MCP 适配器已经把 MCP 工具转换成 LangChain 工具，因此 `ToolNode` 不需要知道工具来自 MCP。

### 检查点 A：创建独立文件

保留计数练习，新建：

```powershell
New-Item lecture\L9\lesson_09_mcp_agent.py -ItemType File
```

不要覆盖 `lesson_09_loop.py`。两个文件分别证明：

```text
lesson_09_loop.py      -> 最小循环与 Checkpointer
lesson_09_mcp_agent.py -> 模型和 MCP 工具的真实循环
```

### 检查点 B：准备模型与 MCP 工具

先从 L7 复用以下内容：

1. `os`、`yaml`、`.env` 和三个模型客户端的导入。
2. 定位 `backend_dir`，加载 `.env`、`config.yaml`。
3. 根据 provider 创建 `model`。
4. `asyncio`、`sys`、`Path` 和 `MultiServerMCPClient`。
5. 在 `main()` 中创建 Client，并执行 `tools = await client.get_tools()`。

不要复制：

- `create_agent` 的导入。
- L7 的 `agent = create_agent(...)`。
- L7 的 `agent.ainvoke(...)`。

L9 将自己构建 Agent 图。

### 检查点 C：让模型支持 MCP 工具

在取得 `tools` 后加入：

```python
model_with_tools = model.bind_tools(tools)
```

`bind_tools()` 不会执行工具。它把工具名称、说明和参数 schema 告诉模型，让模型可以返回 `tool_calls`。

定义模型节点：

```python
async def call_model(state: MessagesState) -> dict:
    """调用模型，并把 AIMessage 追加到消息 State。"""
    response = await model_with_tools.ainvoke(state["messages"])
    return {"messages": [response]}
```

为什么返回列表：`MessagesState` 会把新消息追加到原消息历史，而不是直接替换全部历史。

### 检查点 D：创建 ToolNode 和 Agent 图

```python
tool_node = ToolNode(tools)

builder = StateGraph(MessagesState)
builder.add_node("agent", call_model)
builder.add_node("tools", tool_node)

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)
```

这里不需要手写映射字典，因为 `tools_condition` 正好返回：

```text
"tools"  -> 名为 tools 的节点
END      -> 结束
```

形成循环的代码是：

```python
builder.add_edge("tools", "agent")
```

工具执行完成后必须回到模型，让模型阅读 ToolMessage 并生成最终回答。

### 检查点 E：运行带 thread_id 的图

```python
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

print("Agent 最终回答：", result["messages"][-1].content)
```

使用 `ainvoke()` 是因为模型和 MCP 通信都是异步操作。

### 检查点 F：观察内部消息循环

在最终回答前加入：

```python
for index, message in enumerate(result["messages"]):
    print(index, type(message).__name__, message.content)
```

时间问题通常能看到：

```text
0 HumanMessage  用户问题
1 AIMessage     content 可能为空，但包含 tool_calls
2 ToolMessage   MCP 工具结果
3 AIMessage     最终自然语言回答
```

普通知识问题通常只有：

```text
0 HumanMessage
1 AIMessage
```

这证明 `tools_condition` 只在模型提出工具调用时进入 ToolNode。

### Checkpointer 在 Agent 图中的意义

在计数图中，它保存 `count`；在 Agent 图中，它保存 `messages` 和图的执行位置。相同 `thread_id` 可以继续同一段对话或恢复被中断的流程。

当前示例每次启动程序都会重新创建 `InMemorySaver`，因此进程退出后仍会丢失。持久化 Checkpointer 留到 SQLite 和工程化课程。

### 真实 Agent 图验收

- [ ] 没有使用 `create_agent()`。
- [ ] MCP 工具来自 `await client.get_tools()`。
- [ ] 使用 `model.bind_tools(tools)` 告诉模型工具 schema。
- [ ] `ToolNode` 能执行 MCP 工具。
- [ ] `tools_condition` 能决定进入工具节点或结束。
- [ ] 工具节点执行后能回到模型节点。
- [ ] 时间问题包含 Human/AI/Tool/AI 消息循环。
- [ ] 普通知识问题不进入 ToolNode。
