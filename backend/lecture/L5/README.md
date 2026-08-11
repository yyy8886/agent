# L5 简单 Agent 与工具调用

L1–L4 中，模型只能生成文字。L5 让模型获得一个受控能力：查询当前时间。

本课按四层学习：

1. 普通 Python 函数。
2. 使用 `@tool` 把函数变成 LangChain 工具。
3. 观察模型产生 `tool_calls`，手动完成工具调用循环。
4. 使用 `create_agent` 自动完成同一循环。

先看懂工具循环，再使用 Agent 封装。本课不提供任意命令执行、任意文件读取或网络请求工具。

## Agent 工具调用的基本流程

```text
用户：现在几点？
        ↓
模型判断需要 get_current_time
        ↓
程序执行 Python 函数（不是模型自己执行）
        ↓
程序把结果交回模型
        ↓
模型组织最终中文回答
```

关键结论：模型只能提出“请调用这个工具和这些参数”，真正执行函数的是我们的 Python 程序。

## 检查点 1：安装顶层 LangChain

你当前安装了 `langchain-core` 和 provider 集成，但没有顶层 `langchain` 包。打开 `pyproject.toml`，在依赖中增加：

```toml
"langchain",
```

依赖片段应包含：

```toml
dependencies = [
    "langchain",
    "langchain-deepseek",
    "langchain-ollama",
    "langchain-openai",
    "python-dotenv",
    "pyyaml",
]
```

安装并验证：

```powershell
python -m pip install -e .
python -c "from langchain.agents import create_agent; print('langchain 正常')"
```

## 检查点 2：复制 L4 脚本

```powershell
Copy-Item lecture\L4\lesson_04_chat.py lecture\L5\lesson_05_tools.py
Get-ChildItem lecture\L5
python -m py_compile lecture\L5\lesson_05_tools.py
```

## L5.1 第一个工具

### 检查点 3：导入工具依赖

增加：

```python
from datetime import datetime

from langchain_core.tools import tool
```

### 检查点 4：定义时间工具

在创建模型之前定义：

```python
@tool
def get_current_time() -> str:
    """返回当前电脑所在时区的日期、时间和时区名称。"""
    now = datetime.now().astimezone()
    return now.isoformat(timespec="seconds")
```

`@tool` 做了三件事：

- 使用函数名作为默认工具名。
- 使用 docstring 告诉模型工具做什么。
- 根据参数和类型提示生成输入 schema。

工具描述必须准确。模型主要通过名称、描述和参数 schema 决定是否调用工具。

### 检查点 5：不经过模型，直接测试工具

暂时在文件末尾加入：

```python
print(get_current_time.invoke({}))
```

运行：

```powershell
python lecture\L5\lesson_05_tools.py
```

预期类似：

```text
2026-08-11T10:30:00+08:00
```

这一步不调用模型、不产生 API 费用。先确认 Python 工具本身正确，再接模型。

## L5.2 让模型提出工具调用

### `bind_tools` 做什么

```python
model_with_tools = model.bind_tools([get_current_time])
```

它把工具名称、描述和参数 schema 告诉模型。它不会自动执行工具。

### 检查点 6：观察 `tool_calls`

删除上一检查点的直接打印，将 L4 的 Prompt、Chain 和聊天循环暂时替换为：

```python
from langchain_core.messages import HumanMessage


model_with_tools = model.bind_tools([get_current_time])

message = HumanMessage(content="现在几点？")
response = model_with_tools.invoke([message])

print("模型文本：", response.content)
print("工具请求：", response.tool_calls)
```

可能看到：

```text
模型文本：
工具请求：[{'name': 'get_current_time', 'args': {}, 'id': '...'}]
```

模型此时通常没有直接回答时间，而是提出调用请求。工具函数仍未执行。

如果 `tool_calls` 为空：

- 当前模型或中转站可能不支持工具调用。
- 工具描述可能不清楚。
- 模型可能直接猜测回答。

先尝试明确问题“请调用工具查询当前时间”，必要时切换到明确支持 tool calling 的模型。

## L5.3 手动完成工具循环

手动执行循环能看清 Agent 的核心原理。

导入：

```python
from langchain_core.messages import HumanMessage
```

将检查点 6 的调用替换为：

```python
tools = [get_current_time]
tools_by_name = {tool.name: tool for tool in tools}
model_with_tools = model.bind_tools(tools)

messages = [HumanMessage(content="现在几点？")]

# 第一次调用：模型决定是否使用工具
ai_message = model_with_tools.invoke(messages)
messages.append(ai_message)

print("模型提出：", ai_message.tool_calls)

# Python 根据模型请求执行工具
for tool_call in ai_message.tool_calls:
    selected_tool = tools_by_name[tool_call["name"]]
    tool_message = selected_tool.invoke(tool_call)
    messages.append(tool_message)
    print("工具结果：", tool_message.content)

# 第二次调用：模型读取工具结果，组织最终回答
final_message = model_with_tools.invoke(messages)
print("最终回答：", final_message.content)
```

消息顺序：

```text
HumanMessage：现在几点
AIMessage：请求 get_current_time
ToolMessage：2026-08-11T...
AIMessage：现在是……
```

为什么必须把第一次 `ai_message` 也放入 messages？因为工具结果需要与模型提出的 tool call id 对应，不能只发送一个孤立的结果。

## L5.4 使用 `create_agent`

手动循环可以封装为 Agent。导入：

```python
from langchain.agents import create_agent
```

创建并调用：

```python
agent = create_agent(
    model=model,
    tools=[get_current_time],
    system_prompt=(
        "你是一名简洁的中文助手。"
        "涉及当前时间时必须调用工具，不得猜测。"
    ),
)

result = agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "现在几点？",
            }
        ]
    }
)

final_message = result["messages"][-1]
print(final_message.content)
```

`create_agent` 自动完成：

```text
调用模型
  -> 检查 tool_calls
  -> 执行工具
  -> 将 ToolMessage 返回模型
  -> 重复，直到模型给出最终回答
```

这里先使用 LangChain 的高层 Agent API。L6 才会学习其背后的状态、节点和边为何适合用 LangGraph 表示。

## L5.5 为什么工具必须受控

时间工具是低风险工具：无参数、无外部写入、无命令执行。

以后添加文件工具时必须：

- 限定允许访问的根目录。
- 使用 `Path.resolve()` 检查路径没有逃逸。
- 先只允许 `.txt`、`.md` 等明确格式。
- 限制读取大小。
- 写入、删除、命令执行需要单独授权。

不要直接提供这种工具：

```python
@tool
def run_any_command(command: str) -> str:
    ...
```

模型生成的参数属于不可信输入。`@tool` 不是安全沙箱。

## Provider 能力差异

三种客户端都可以绑定工具，但具体模型未必支持同等能力：

| Provider | 注意事项 |
| --- | --- |
| DeepSeek | 以所选模型的 tool calling 文档为准 |
| OpenAI/中转站 | 中转站可能不完整转发 tools 字段 |
| Ollama | 取决于本地模型是否支持工具调用 |

“客户端有 `.bind_tools()`”不等于“当前模型一定会正确调用工具”。

## 常见问题

| 现象 | 原因 | 处理方法 |
| --- | --- | --- |
| 找不到 `langchain.agents` | 未安装顶层 langchain | 更新 pyproject 后重新安装 |
| `tool_calls` 为空 | 模型/代理不支持或描述不清 | 明确要求调用，换支持的模型验证 |
| 工具没有执行 | `bind_tools` 只告诉模型工具定义 | 手动执行或使用 create_agent |
| `KeyError` 工具名 | 模型请求了未注册工具 | 只执行 `tools_by_name` 中的工具 |
| ToolMessage 对不上 | 没保留第一次 AIMessage | 按完整消息顺序追加 |
| 时间正确但格式不好 | 工具只返回机器格式 | 让模型根据 ToolMessage 组织自然语言 |

## 小练习

1. 直接调用时间工具，证明它不依赖模型。
2. 打印 `get_current_time.name` 和 `get_current_time.description`。
3. 比较“你好”和“现在几点”的 `tool_calls`。
4. 给工具写一个模糊 docstring，观察选择变化后恢复。
5. 画出 HumanMessage、AIMessage、ToolMessage、最终 AIMessage 的顺序。

## L5 验收

- [ ] 能解释模型只提出工具请求，Python 才真正执行。
- [ ] 时间工具可以独立运行。
- [ ] 能读取 `response.tool_calls`。
- [ ] 能手动完成一次工具调用循环。
- [ ] 能使用 `create_agent` 得到最终回答。
- [ ] 能解释为什么不能提供任意命令工具。
- [ ] 能说明 provider 客户端支持绑定工具，不代表具体模型支持。

完成后进入 L6，学习何时需要 LangGraph，以及 Agent 循环如何表示成状态图。
