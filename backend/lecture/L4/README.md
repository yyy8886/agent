# L4 连续对话、内存历史与流式输出

L3 的 Chain 每次只回答一个问题。L4 将它改造成命令行聊天程序。

本课学习：

1. 使用 `while` 循环持续接收输入。
2. 用消息列表保存本次运行的历史。
3. 用 `MessagesPlaceholder` 把历史交给 Prompt。
4. 使用 `.stream()` 逐段输出回答。

本课历史只存在内存，关闭程序后会消失。SQLite 持久化放在 L16。

## 完成本课后的目录

```text
backend/lecture/
├─ L3/lesson_03_chain.py
└─ L4/
   ├─ README.md
   └─ lesson_04_chat.py       # 由你在检查点 1 创建
```

## L4.1 记忆的基础原理

模型只能看到当前请求传入的数据。如果第二次调用时不再发送第一句话，它就不知道第一句话发生过。

```text
把以前的用户消息和 AI 消息保存到 list
        ↓
下一次请求时把整个 list 再发送给模型
```

### 检查点 1：复制 L3 脚本

在 `backend` 目录执行：

```powershell
Copy-Item lecture\L3\lesson_03_chain.py lecture\L4\lesson_04_chat.py
Get-ChildItem lecture\L4
python -m py_compile lecture\L4\lesson_04_chat.py
```

## L4.2 为历史预留位置

### 检查点 2：修改导入

将：

```python
from langchain_core.prompts import ChatPromptTemplate
```

替换为：

```python
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
```

- `HumanMessage`：保存用户输入。
- `AIMessage`：保存模型回答。
- `MessagesPlaceholder`：在 Prompt 中预留历史消息的位置。

### 检查点 3：修改 Prompt

保留创建 `model` 的代码。将 Prompt 到 Chain 的部分改为：

```python
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一名耐心的 Python 入门教师。"
            "使用简体中文，回答清晰但不过度冗长。",
        ),
        MessagesPlaceholder("history"),
        ("human", "{question}"),
    ]
)

parser = StrOutputParser()
chain = prompt | model | parser
```

结构：

```text
SystemMessage：固定规则
MessagesPlaceholder("history")：过去消息，开始时为空
HumanMessage：本次问题
```

Placeholder 的名称必须和以后传给 Chain 的字典键名相同。

## L4.3 用 `invoke()` 连续聊天

### 检查点 4：加入循环

将 `question = input(...)` 开始到文件末尾替换为：

```python
history = []

print("输入 exit 或 quit 结束对话。")

while True:
    question = input("你：").strip()

    if question.lower() in {"exit", "quit"}:
        print("对话结束。")
        break

    if not question:
        print("输入不能为空。")
        continue

    answer = chain.invoke(
        {
            "history": history,
            "question": question,
        }
    )

    print(f"{provider}：{answer}")

    history.append(HumanMessage(content=question))
    history.append(AIMessage(content=answer))
```

`history = []` 必须位于循环外，否则每轮开始都会清空历史。

### 检查点 5：验证历史

运行：

```powershell
python lecture\L4\lesson_04_chat.py
```

依次输入：

```text
我叫小明
我叫什么名字？
exit
```

第二个回答应包含“小明”：

```text
第一轮结束：history 添加 HumanMessage + AIMessage
第二轮开始：history 插入 Prompt，模型再次看到第一轮
```

重新启动脚本后，`history = []` 会再次执行，名字会消失。这是本课预期。

## L4.4 使用 `stream()` 流式输出

```text
invoke()：等待完整回答，再一次性返回
stream()：每生成一段内容，就立刻交给程序
```

将循环中的 `answer = chain.invoke(...)` 和打印部分替换为：

```python
print(f"{provider}：", end="", flush=True)

parts = []
for chunk in chain.stream(
    {
        "history": history,
        "question": question,
    }
):
    print(chunk, end="", flush=True)
    parts.append(str(chunk))

print()
answer = "".join(parts)
```

历史追加仍保持：

```python
history.append(HumanMessage(content=question))
history.append(AIMessage(content=answer))
```

`parts` 用于收集流式片段，`"".join(parts)` 将它们恢复为完整回答，供下一轮历史使用。

### 检查点 6：验证流式效果

运行并输入：

```text
用三个步骤解释如何学习 Python 函数。
```

回答应逐段出现。若 provider 或中转站缓冲响应，可能仍一次性显示，这属于服务端能力差异。

## L4.5 历史长度与成本

每一轮都会重新发送历史：

```text
第 1 轮：system + 第 1 轮
第 2 轮：system + 第 1 轮 + 第 2 轮
第 20 轮：system + 前 19 轮 + 第 20 轮
```

历史越长，token 成本和延迟通常越高。后续会学习历史裁剪、摘要、检索和 SQLite 持久化。

不要把 API Key、密码或无关大文档放入聊天历史。

## 常见问题

| 现象 | 原因 | 处理方法 |
| --- | --- | --- |
| 模型不记得名字 | history 没传入或没有追加 | 检查键名和 append 顺序 |
| `KeyError: history` | Placeholder 和输入键不同 | 两处都使用 `history` |
| 退出后名字消失 | 历史只在内存 | 这是本课预期 |
| 流式后历史为空 | 没有拼回完整 answer | 保留 `parts` 和 `join` |
| 没有流式效果 | provider/代理缓冲 | 换支持 streaming 的服务验证 |

## 小练习

1. 告诉模型喜欢的语言，下一轮再询问。
2. 每轮打印 `len(history)`，观察增加两条消息。
3. 输入空行，确认不发送请求。
4. 临时把 `history = []` 放进循环，观察失忆，再改回。
5. 比较 `invoke()` 与 `stream()` 的体验。

## L4 验收

- [ ] 能解释 `MessagesPlaceholder`。
- [ ] 连续两轮能引用第一轮信息。
- [ ] 能解释重启后历史为何消失。
- [ ] 能说明历史为何增加 token 成本。
- [ ] 流式片段能拼成完整 answer 并保存。
- [ ] 能区分 `invoke()` 和 `stream()`。

完成后进入 L5。L5 才会让模型调用受控工具。
