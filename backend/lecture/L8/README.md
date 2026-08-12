# L8 LangGraph：第一个 StateGraph

L7 的 Agent 已经可以自动选择 MCP 工具，但它内部的执行过程主要由 Agent 框架管理。遇到更复杂的任务时，我们通常需要明确控制：

- 当前流程保存了哪些数据。
- 下一步执行哪个步骤。
- 什么条件下走不同分支。
- 是否循环、暂停或等待人工确认。

LangGraph 用一张图表示这些流程。本课只创建最小的 `StateGraph`，先理解图的结构，再在后续课程加入模型、工具、循环和持久化。

## 这一课解决什么问题

我们做一个最小流程：

```text
用户输入
   ↓
读取问题节点
   ↓
生成回答节点
   ↓
输出结果
```

这里的回答先由 Python 函数生成，不连接大模型。这样可以先观察 LangGraph 的运行方式。

## LangGraph 的三个核心概念

### State：流程共享的数据

State 是一个字典结构，保存流程运行时的数据，例如：

```python
{
    "question": "什么是 Python？",
    "answer": "Python 是一种编程语言。"
}
```

每个节点都可以读取 State，并返回需要更新的字段。

### Node：一个处理步骤

Node 通常是一个 Python 函数：

```python
def answer_node(state):
    return {"answer": "这是回答"}
```

节点不需要手动修改整个 State，只返回本次要更新的内容。

### Edge：节点之间的连接

Edge 决定执行顺序：

```text
START -> read_question -> answer -> END
```

后续还会学习条件边，例如：问题需要检索时走 RAG，不需要检索时直接回答。

## 检查点 1：确认 LangGraph 安装

在 `backend` 目录运行：

```powershell
python -c "import langgraph; print('LangGraph 正常')"
```

预期输出：

```text
LangGraph 正常
```

## 检查点 2：创建课程文件

在 `backend` 目录运行：

```powershell
New-Item lecture\L8 -ItemType Directory -Force
New-Item lecture\L8\lesson_08_graph.py -ItemType File
```

## 检查点 3：写第一个 StateGraph

在 `lesson_08_graph.py` 写入：

```python
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class LessonState(TypedDict, total=False):
    question: str
    answer: str


def read_question(state: LessonState) -> dict:
    """读取并保留用户问题。"""
    return {"question": state["question"].strip()}


def answer_question(state: LessonState) -> dict:
    """先用普通 Python 函数生成一个固定回答。"""
    return {"answer": f"你问的是：{state['question']}"}


builder = StateGraph(LessonState)
builder.add_node("read_question", read_question)
builder.add_node("answer_question", answer_question)
builder.add_edge(START, "read_question")
builder.add_edge("read_question", "answer_question")
builder.add_edge("answer_question", END)

graph = builder.compile()

result = graph.invoke({"question": "  什么是 Python？  "})
print(result)
```

逐段理解：

- `TypedDict` 描述 State 允许有哪些字段。
- `StateGraph(LessonState)` 创建图构建器。
- `add_node` 注册节点名称和函数。
- `START` 是图的入口，`END` 是图的出口。
- `compile()` 把构建器编译成可运行的图。
- `graph.invoke(...)` 运行一次完整流程。

运行：

```powershell
python -m py_compile lecture\L8\lesson_08_graph.py
python lecture\L8\lesson_08_graph.py
```

预期输出类似：

```text
{'question': '什么是 Python？', 'answer': '你问的是：什么是 Python？'}
```

## 运行过程

```text
graph.invoke 初始 State
  -> START
  -> read_question 更新 question
  -> answer_question 更新 answer
  -> END
  -> 返回完整 State
```

LangGraph 会把节点返回的字典合并到 State 中。因此第一个节点返回 `question`，第二个节点可以读取它并生成 `answer`。

## 和普通函数调用的区别

普通代码可以直接写：

```python
question = read_question(...)
answer = answer_question(question)
```

LangGraph 的价值是把顺序显式保存为图。后续增加条件分支、循环、检查点和人工审批时，不需要把所有逻辑塞进一个巨大函数。

## 常见错误

### `KeyError: 'question'`

运行时初始 State 没有传入 `question`：

```python
graph.invoke({})
```

应传入：

```python
graph.invoke({"question": "你的问题"})
```

### 节点没有返回字典

节点应返回 State 更新内容：

```python
return {"answer": "..."}
```

不要只 `print` 而不返回结果。

### 忘记连接 START 或 END

没有入口或出口，图无法按预期执行。最小流程必须包含：

```python
builder.add_edge(START, "第一个节点")
builder.add_edge("最后一个节点", END)
```

## 检查点 4：加入第一个条件分支

现在把固定流程：

```text
read_question -> answer_question
```

改成：

```text
                         -> answer_python  -> END
START -> read_question
                         -> answer_general -> END
```

路由规则保持简单：问题中包含 `Python` 时走 `answer_python`，否则走 `answer_general`。

### 第一步：把原回答节点改成两个节点

删除原来的 `answer_question()`，换成：

```python
def answer_python(state: LessonState) -> dict:
    """回答 Python 相关问题。"""
    print("正在执行：answer_python")
    return {"answer": f"这是一个 Python 问题：{state['question']}"}


def answer_general(state: LessonState) -> dict:
    """回答其他类型的问题。"""
    print("正在执行：answer_general")
    return {"answer": f"这是一个普通问题：{state['question']}"}
```

### 第二步：编写路由函数

在两个回答节点后加入：

```python
def route_question(state: LessonState) -> str:
    """根据问题内容选择下一个节点。"""
    if "python" in state["question"].lower():
        return "python"
    return "general"
```

路由函数不生成回答，只返回一个选择标签：

```text
python  -> Python 分支
general -> 通用分支
```

使用 `.lower()` 后，`Python`、`PYTHON` 和 `python` 都可以匹配。

### 第三步：注册节点并连接条件边

把原来的构图部分替换为：

```python
builder = StateGraph(LessonState)

builder.add_node("read_question", read_question)
builder.add_node("answer_python", answer_python)
builder.add_node("answer_general", answer_general)

builder.add_edge(START, "read_question")

builder.add_conditional_edges(
    "read_question",
    route_question,
    {
        "python": "answer_python",
        "general": "answer_general",
    },
)

builder.add_edge("answer_python", END)
builder.add_edge("answer_general", END)
```

`add_conditional_edges()` 的三个参数分别是：

1. `read_question`：哪个节点执行完后进行判断。
2. `route_question`：用哪个函数进行判断。
3. 映射字典：路由标签分别对应哪个节点。

执行过程：

```text
read_question 更新 State
  -> route_question 读取更新后的 State
  -> 返回 "python" 或 "general"
  -> 映射到对应回答节点
```

### 第四步：验证两个分支

先测试：

```python
result = graph.invoke({"question": "什么是 Python？"})
```

预期：

```text
正在执行：read_question
正在执行：answer_python
```

再改成：

```python
result = graph.invoke({"question": "今天天气怎么样？"})
```

预期：

```text
正在执行：read_question
正在执行：answer_general
```

一次运行只会进入一个回答节点，不会同时执行两个分支。

### 普通 Edge 和条件 Edge 的区别

```text
add_edge：下一个节点固定
add_conditional_edges：下一个节点由 State 和路由函数决定
```

当前路由规则是普通 Python 判断。后续可以让模型分类，也可以根据工具结果、检索结果或用户权限进行路由。

## L8 验收目标

- [ ] 能解释 State、Node、Edge 的区别。
- [ ] 能创建 `TypedDict` State。
- [ ] 能注册两个节点并连接 `START`、`END`。
- [ ] 能编译并运行 `StateGraph`。
- [ ] 能使用 `add_conditional_edges()` 让两个问题走不同分支。
- [ ] 能说出为什么 LangGraph 适合分支、循环和可恢复流程。

本课不接入 MCP、不接入 RAG，也不创建复杂 Agent。L9 再学习循环、Checkpointer，以及如何把模型和工具放入图中。
