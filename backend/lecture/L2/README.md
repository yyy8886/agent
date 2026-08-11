# L2 消息、角色提示词与基础参数

L1 已经解决：选中一个模型，发送字符串，获得一次回复。

L2 只在这个基础上增加三件事：

1. 理解 `SystemMessage`、`HumanMessage`、`AIMessage`。
2. 使用 system 消息规定模型扮演什么角色、怎样回答。
3. 理解 `temperature`、`timeout_seconds`、`max_retries`。

本课不学习 Chain、不做自动记忆、不引入 Agent。完成一个检查点后再继续。

## 完成本课后的目录

```text
backend/
├─ config.yaml
├─ .env
└─ lecture/
   ├─ L1/
   │  └─ lesson_01_chat.py
   └─ L2/
      ├─ README.md
      └─ lesson_02_messages.py    # 由你在检查点 1 创建
```

## L2.1 为什么需要“消息角色”

### L1 的调用方式

L1 使用：

```python
response = model.invoke(question)
```

传入普通字符串时，LangChain 会把它当成用户消息。它适合最简单的问答，但没有明确告诉模型：

- 你是谁？
- 应该用什么风格回答？
- 哪些要求长期有效？

### 三种消息

```text
SystemMessage：开发者给模型的角色和长期规则
HumanMessage：用户本次输入的内容
AIMessage：模型以前回复过的内容
```

例如：

```text
SystemMessage：你是一名 Python 入门教师，使用简体中文，先解释再举例。
HumanMessage：什么是变量？
AIMessage：变量可以理解为保存数据的名字……
```

这里的 `SystemMessage` 不是“权限绝对最高、永远无法违反”的安全机制。它只是模型上下文中的高优先级指令，程序仍需自己做权限检查和输入验证。

## 检查点 1：复制 L1 脚本

保持 PowerShell 位于 `backend` 目录，执行：

```powershell
Copy-Item lecture\L1\lesson_01_chat.py lecture\L2\lesson_02_messages.py
Get-ChildItem lecture\L2
```

为什么复制而不是直接修改 L1？

- L1 的成果保持可运行。
- L2 只展示本课新增内容。
- 出错时可以对比两个版本。

不要运行 `README.md`，要运行的是 `.py` 文件。

## 检查点 2：导入消息类型

打开 `lecture/L2/lesson_02_messages.py`。

在 LangChain 客户端导入附近增加：

```python
from langchain_core.messages import HumanMessage, SystemMessage
```

本检查点暂时没有使用 `AIMessage`。我们先看清 system 和 human 两个角色，再加入历史消息。

## 检查点 3：把字符串改成消息列表

找到脚本最后的交互代码：

```python
question = input("你：").strip()
if not question:
    raise SystemExit("输入不能为空")

response = model.invoke(question)
print(f"{provider}：{response.content}")
```

将它替换为：

```python
question = input("你：").strip()
if not question:
    raise SystemExit("输入不能为空")

messages = [
    SystemMessage(
        content="你是一名耐心的 Python 入门教师。使用简体中文，先解释概念，再给一个简短例子。"
    ),
    HumanMessage(content=question),
]

response = model.invoke(messages)
print(f"{provider}：{response.content}")
```

现在 `model.invoke()` 收到的不再是一个字符串，而是按顺序排列的消息列表：

```text
messages[0] -> SystemMessage -> 回答规则
messages[1] -> HumanMessage  -> 用户问题
```

顺序很重要。模型按照整个上下文理解对话。

## 检查点 4：运行并比较

从 `backend` 目录运行：

```powershell
python lecture\L2\lesson_02_messages.py
```

输入：

```text
什么是 Python 变量？
```

观察回答是否符合两条 system 要求：

1. 先解释概念。
2. 再给一个简短例子。

然后只修改 system 内容，例如：

```python
content="你是一名代码审查员。回答不超过三句话，不提供完整代码。"
```

再次询问同一问题，比较回答结构。这个实验说明：用户问题没有变化，system 消息改变了模型的回答方式。

## L2.2 `AIMessage` 与手动对话历史

模型不会自动记住上一次运行脚本发生了什么。所谓“对话记忆”，本质上是程序再次把以前的消息发送给模型。

导入 `AIMessage`：

```python
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
```

临时把 `messages` 改为：

```python
messages = [
    SystemMessage(content="你是一名简洁的中文助手。"),
    HumanMessage(content="我叫小明。"),
    AIMessage(content="你好，小明！"),
    HumanMessage(content="我叫什么名字？"),
]

response = model.invoke(messages)
print(response.content)
```

模型能回答“小明”，不是因为模型永久保存了名字，而是因为程序把这段历史重新放进了消息列表。

本课只是手动演示消息历史。L4 才会实现聊天循环、session 和自动管理历史。

### 消息顺序图

```text
SystemMessage：回答规则
      ↓
HumanMessage：我叫小明
      ↓
AIMessage：你好，小明
      ↓
HumanMessage：我叫什么名字
      ↓
模型生成新的 AIMessage
```

## L2.3 三个基础参数

这些参数已经位于 `config.yaml`，现在正式理解它们。

### `temperature`

```yaml
temperature: 0.2
```

它影响输出的随机程度：

- 较低：通常更稳定，适合代码、提取、分类和事实问答。
- 较高：通常更多样，适合头脑风暴和创意文本。
- 它不保证事实正确，也不是回答质量的百分比。

不同 provider 对参数范围和实现可能不同，应以对应模型文档为准。

### `timeout_seconds`

```yaml
timeout_seconds: 60
```

表示客户端最多等待一次请求多长时间。它解决“网络请求一直不返回”的问题，不限制模型生成内容的长度。

### `max_retries`

```yaml
max_retries: 2
```

表示遇到某些临时失败时最多重试多少次。重试适合短暂网络错误或限流，不应掩盖密钥错误、模型 ID 错误等永久问题。

### 参数实验

使用同一个问题：

```text
给我的桌面 AI 助手起三个名字，并说明理由。
```

分别尝试：

```yaml
temperature: 0
```

和：

```yaml
temperature: 1
```

每组运行两次，观察措辞和结果变化。实验后建议恢复为 `0.2`。

## 常见问题

| 现象                         | 原因                             | 处理方法                             |
| ---------------------------- | -------------------------------- | ------------------------------------ |
| `NameError: SystemMessage` | 忘记导入                         | 检查`langchain_core.messages` 导入 |
| 回复不符合角色               | system 指令模糊或互相冲突        | 改成明确、可检查的要求               |
| 模型不记得上次运行           | 脚本没有保存和重发历史           | 本课用消息列表手动演示，L4 再自动化  |
| 修改 temperature 没明显变化  | 问题过于确定或 provider 实现不同 | 换开放问题，多运行几次比较           |
| 超时后仍然重试               | `max_retries` 大于 0           | 理解 timeout 和 retry 是两个设置     |

## 小练习

1. 编写一个“只解释 Python，不回答其他主题”的 system 消息。
2. 输入一个非 Python 问题，观察模型是否遵守要求。
3. 让 system 要求回答包含“定义、例子、注意事项”三个部分。
4. 手动加入一组 Human/AI 历史，让模型回答历史中的信息。
5. 用自己的话解释为什么消息历史会增加 token 消耗。

## L2 验收

- [X] 能解释 System/Human/AI 三种消息的职责。
- [X] `lesson_02_messages.py` 可以使用消息列表调用当前模型。
- [X] 能通过 system 消息改变回答方式。
- [X] 能解释模型记住“小明”是因为历史被重新发送。
- [X] 能解释 temperature、timeout、max_retries 的区别。
- [X] 能说明 system 消息不能代替程序权限控制。

完成验收后再进入 L3。L3 将学习 `ChatPromptTemplate`、LCEL Chain 和输出解析，不在 L2 提前加入。
