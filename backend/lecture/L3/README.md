# L3 Prompt、Chain 与输出解析

L1 学会创建和切换模型，L2 学会消息角色。L3 解决“每次手写消息列表不方便复用”的问题。

本课依次学习：

1. `ChatPromptTemplate`：制作包含变量的消息模板。
2. PromptValue：观察模板填入变量后生成了什么。
3. `StrOutputParser`：把 `AIMessage` 转成普通字符串。
4. LCEL：使用 `prompt | model | parser` 连接完整流程。
5. 最后再认识 model factory，不在开头增加抽象。

## 完成本课后的目录

```text
backend/lecture/
├─ L2/
│  └─ lesson_02_messages.py
└─ L3/
   ├─ README.md
   └─ lesson_03_chain.py       # 由你在检查点 1 创建
```

## L3.1 从消息列表到 Prompt 模板

L2 直接写死消息：

```python
messages = [
    SystemMessage(content="你是一名简洁的中文助手。"),
    HumanMessage(content="请给我起一个昵称。"),
]
```

如果角色和问题经常变化，就要反复修改代码。Prompt 模板会固定结构，把变化部分留成变量：

```text
你是一名 {role}，使用 {style} 回答 {question}
```

### 检查点 1：复制 L2 脚本

在 `backend` 目录执行：

```powershell
Copy-Item lecture\L2\lesson_02_messages.py lecture\L3\lesson_03_chain.py
Get-ChildItem lecture\L3
python -m py_compile lecture\L3\lesson_03_chain.py
```

### 检查点 2：导入模板

增加：

```python
from langchain_core.prompts import ChatPromptTemplate
```

L3 暂时不手动创建三种消息，可以删除：

```python
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
```

### 检查点 3：只生成 PromptValue

保留脚本前面加载配置、创建模型的代码。把最后的手动消息和模型调用替换为：

```python
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一名{role}。使用{style}回答，先解释概念，再给一个简短例子。",
        ),
        ("human", "{question}"),
    ]
)

prompt_value = prompt.invoke(
    {
        "role": "Python 入门教师",
        "style": "简体中文",
        "question": "什么是 Python 列表？",
    }
)

print(prompt_value)
```

运行：

```powershell
python lecture\L3\lesson_03_chain.py
```

预期看到 SystemMessage 和 HumanMessage。此时没有调用模型，不产生 API 费用。

```text
ChatPromptTemplate（未填变量）
        ↓ prompt.invoke(dict)
ChatPromptValue（已填好变量的消息集合）
        ↓ .messages
SystemMessage + HumanMessage
```

模板有 `{question}` 时，调用字典必须提供完全同名的 `question`。变量名区分大小写。

## L3.2 模板连接模型

确认 PromptValue 正确后，将最后的打印改为：

```python
response = model.invoke(prompt_value)
print(type(response))
print(response.content)
```

数据变化：

```text
dict -> prompt.invoke() -> ChatPromptValue
ChatPromptValue -> model.invoke() -> AIMessage
```

运行后，`type(response)` 应显示 AIMessage 类型；展示文字仍使用 `response.content`。

## L3.3 输出解析器

模型返回 AIMessage，其中可能包含文本、token 使用情况、工具调用等元数据。如果当前只需要字符串，可以使用解析器。

导入：

```python
from langchain_core.output_parsers import StrOutputParser
```

使用：

```python
parser = StrOutputParser()
text = parser.invoke(response)

print(type(text))
print(text)
```

预期：

```text
AIMessage -> StrOutputParser -> str
```

`StrOutputParser` 只转换格式，不判断答案是否正确。

## L3.4 使用 LCEL 组成 Chain

前面分别执行了三步：

```python
prompt_value = prompt.invoke(data)
response = model.invoke(prompt_value)
text = parser.invoke(response)
```

LCEL 使用 `|` 将它们连接：

```python
chain = prompt | model | parser
```

这里的 `|` 表示“把左边输出交给右边输入”，不是“或者”。

最终交互代码：

```python
chain = prompt | model | parser

question = input("你：").strip()
if not question:
    raise SystemExit("输入不能为空")

answer = chain.invoke(
    {
        "role": "Python 入门教师",
        "style": "简体中文",
        "question": question,
    }
)

print(f"{provider}：{answer}")
```

`answer` 已经是字符串，不再使用 `answer.content`。

### 完整数据流

```text
输入 dict
  -> ChatPromptTemplate
  -> ChatPromptValue
  -> ChatModel
  -> AIMessage
  -> StrOutputParser
  -> str
```

能解释每一步的数据类型，比背下 `prompt | model | parser` 更重要。

## L3.5 model factory 为什么放最后

L1–L3 都复制了较长的 provider 创建代码。完成 Chain 后，我们会把它移动到单独函数：

```python
model = create_model(config)
```

再比较 LangChain 的 `init_chat_model`。现在不立刻重构，因为同时学习模板、Chain、模块导入和包结构会增加理解负担。

## 常见问题

| 现象                              | 原因                 | 处理方法                                    |
| --------------------------------- | -------------------- | ------------------------------------------- |
| Prompt 缺少变量                   | 模板和调用字典不一致 | 对照`{role}`、`{style}`、`{question}` |
| `NameError: ChatPromptTemplate` | 忘记导入             | 检查`langchain_core.prompts`              |
| 输入类型错误                      | 把错误对象传给下一步 | 打印每一步的`type(...)`                   |
| parser 后访问`.content`         | parser 已返回字符串  | 直接打印`answer`                          |
| 回答仍像 L2                       | 运行了错误文件       | 确认运行`lesson_03_chain.py`              |

## 小练习

1. 把 role 改为“代码审查员”，比较回答。
2. 增加 `{language}` 变量，并在调用字典传值。
3. 故意漏掉一个变量，阅读报错后恢复。
4. 分别打印 PromptValue、AIMessage、str 的类型。
5. 用自己的话画出 `dict -> Prompt -> Model -> Parser -> str`。

## L3 验收

- [X] 能解释模板与普通消息列表的区别。
- [X] 能说明 `prompt.invoke()` 为什么不会调用模型。
- [X] 能说出 PromptValue、AIMessage、str 的变化顺序。
- [X] 能独立写出 `prompt | model | parser`。
- [X] 知道 parser 负责格式转换，不负责事实校验。
- [ ] 能解释为什么 model factory 放在本课最后。

完成后再进入 L4。L4 才会建立命令行聊天循环和自动管理会话历史。
