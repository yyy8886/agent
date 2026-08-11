# L7 MCP Client：让 LangChain Agent 使用 MCP 工具

L6 中，我们写了一个独立的 MCP Server，并用 Inspector 和 VS Code 验证了它：

```text
Inspector / VS Code
        │ MCP
        ▼
mcp_server.py
        └─ get_current_time
```

这一课要把 Inspector 换成我们自己的 Python 程序：

```text
用户
  ↓
LangChain Agent（MCP Client）
  ↓ 判断是否需要工具
MCP Server（L6）
  ↓
get_current_time
```

本课结束时，你的 Agent 将能回答“现在几点”，但工具并不写在 Agent 文件里，而是来自 L6 的 MCP Server。

## 先理解：为什么还要写 MCP Client

L6 的 `mcp_server.py` 只是提供能力。它不会主动连接模型，也不会主动回答用户。

MCP Client 负责：

1. 启动或连接 MCP Server。
2. 完成 MCP 初始化握手。
3. 查询 Server 提供了哪些工具。
4. 把 MCP 工具转换为 LangChain 能识别的工具。
5. 在程序结束时关闭连接和子进程。

Agent 负责判断“什么时候使用哪个工具”。MCP Client 负责把 Agent 的工具请求送到 MCP Server。两者不是同一个概念。

## L5 与 L7 的区别

L5 的工具和 Agent 在同一个 Python 程序中：

```python
@tool
def get_current_time() -> str:
    ...
```

L7 不再复制这个函数。Agent 通过 MCP 使用 L6 已经暴露的函数：

```text
L5：Agent -> 本地 @tool 函数
L7：Agent -> MCP Client -> MCP Server -> 工具函数
```

这样做的价值是，同一个 MCP Server 可以被 Python Agent、VS Code 和未来的桌宠共同使用。

## 本课学习路线

1. 安装 LangChain 的 MCP 适配器。
2. 创建 MCP Client 配置。
3. 先只连接 Server 并打印工具列表。
4. 再把 MCP 工具交给 `create_agent`。
5. 让 Agent 自动调用 `get_current_time`。
6. 理解异步、连接生命周期和常见错误。

不要直接跳到第 4 步。先验证工具发现，可以把“连接问题”和“模型问题”分开排查。

## 检查点 1：安装 MCP 适配器

我们已经安装了两类依赖：

- `mcp`：官方 MCP SDK，用来实现协议和 Server。
- `langchain`：模型、消息、工具和 Agent。

现在还缺少连接两者的适配器：

```text
langchain-mcp-adapters
```

打开 `backend/pyproject.toml`，在 `dependencies` 中加入：

```toml
"langchain-mcp-adapters",
```

加入后，依赖部分应包含：

```toml
dependencies = [
    "langchain",
    "langchain-deepseek",
    "langchain-mcp-adapters",
    "langchain-ollama",
    "langchain-openai",
    "mcp[cli]",
    "python-dotenv",
    "pyyaml",
]
```

然后在 `backend` 目录执行：

```powershell
python -m pip install -e .
```

验证安装：

```powershell
python -c "from langchain_mcp_adapters.client import MultiServerMCPClient; print('MCP 适配器正常')"
```

预期输出：

```text
MCP 适配器正常
```

### 为什么包名和 import 名不同

安装名称使用连字符：

```text
langchain-mcp-adapters
```

Python 导入名称使用下划线：

```python
langchain_mcp_adapters
```

这是 Python 包中很常见的命名方式，不是安装了两个不同的库。

## 检查点 2：创建课程文件

确认检查点 1 成功后，再在 `backend` 目录执行：

```powershell
New-Item lecture\L7\lesson_07_mcp_client.py -ItemType File
```

检查：

```powershell
Get-ChildItem lecture\L7
```

此时应看到：

```text
README.md
lesson_07_mcp_client.py
```

先不要复制 L5 的代码。我们要先写一个不调用模型的最小 MCP Client。

## 检查点 3：只发现 MCP 工具

完成前两个检查点后再学习这一段。

客户端会使用 `MultiServerMCPClient`。虽然本课只有一个 Server，这个类仍允许未来同时连接文件、数据库等多个 MCP Server。

配置的核心结构是：

```python
{
    "给客户端看的服务器名称": {
        "transport": "stdio",
        "command": "启动程序",
        "args": ["传给程序的参数"],
    }
}
```

本课中：

- Server 名称是 `lesson-tools`。
- transport 是 `stdio`。
- command 使用当前虚拟环境的 Python。
- args 指向 L6 的 `mcp_server.py`。

我们会用 `sys.executable` 取得当前正在运行的 Python 路径，避免误用系统 Python：

```python
import sys

print(sys.executable)
```

完整代码会在你完成检查点 1 和检查点 2 后逐行编写。第一次运行只应打印发现的工具名称，不会调用模型，也不会调用工具。

## 为什么代码会出现 async 和 await

MCP Client 需要启动进程、发送请求并等待响应，这些操作不是瞬间完成的。Python 使用异步语法表达这种等待：

```python
async def main():
    tools = await client.get_tools()
```

先把它理解成：

```text
async def：这个函数里面允许等待网络或进程通信
await：等待结果返回，但用异步方式管理等待
asyncio.run(main())：从普通 Python 程序进入异步程序
```

本课不深入异步原理。后面 FastAPI 和 WebSocket 还会再次使用它。

## 检查点 4：把 MCP 工具交给 Agent

工具发现成功后，我们才会接入 L5 学过的 `create_agent`：

```text
client.get_tools()
  -> 得到 LangChain 工具列表
  -> create_agent(model, tools)
  -> Agent 根据用户问题选择工具
```

模型切换仍沿用 L1 的方式：读取 `config.yaml`，根据 provider 创建模型。MCP 不负责选择 DeepSeek、OpenAI 或 Ollama，也不会替代模型配置。

这一阶段的目标问题是：

```text
请使用工具告诉我当前时间。
```

预期流程：

```text
用户提问
  -> 模型提出 get_current_time 工具调用
  -> MCP Client 把调用发给 L6 Server
  -> Server 执行函数并返回时间
  -> 模型组织最终中文回答
```

## 常见错误预告

### 找不到 `langchain_mcp_adapters`

说明适配器没有安装到当前虚拟环境。确认终端前有 `(.venv)`，再运行：

```powershell
python -m pip install -e .
```

### Server 启动后立刻断开

常见原因：

- `args` 中的文件路径写错。
- command 启动了没有安装 `mcp` 的系统 Python。
- `mcp_server.py` 有语法错误。
- Server 在 stdout 中打印了普通日志，破坏 stdio 协议。

### 为什么不用先运行 `mcp_server.py`

stdio 模式下，Client 会根据 command 和 args 启动 Server 子进程。通常不需要先开另一个终端运行 Server。

Inspector、VS Code 和本课 Client 各自连接时，可能各自启动一个 Server 进程。这是 stdio 模式的正常行为。

### 工具能发现，但 Agent 不调用

这时 MCP 通信通常已经正常，问题更可能在：

- 用户问题不需要工具。
- 模型不支持或没有正确生成工具调用。
- 工具名称、描述不够清楚。
- 使用的 OpenAI 兼容服务没有完整实现 tool calling。

先用“请使用工具告诉我当前时间”做明确测试，再测试自然表达。

## 安全边界

MCP 让工具更容易接入，但不会自动保证安全：

- Client 只能连接明确配置的 Server。
- 不把 API Key 放进客户端代码或 MCP 配置。
- 对写文件、执行命令、删除内容等工具增加用户确认。
- 不把模型给出的任意字符串直接拼成系统命令。
- 工具结果也属于外部输入，不能默认完全可信。

本课只使用读取当前时间的低风险工具。

## L7 验收目标

- [ ] 能解释 MCP Server、MCP Client 和 Agent 各自负责什么。
- [ ] 能导入 `MultiServerMCPClient`。
- [ ] 能通过 stdio 启动 L6 Server。
- [ ] 能打印 Client 发现的 `get_current_time` 工具。
- [ ] 能把 MCP 工具交给 LangChain Agent。
- [ ] Agent 能通过 MCP 工具回答当前时间。
- [ ] 程序退出后没有遗留异常或未关闭会话的警告。

完成 L7 后，L8 才开始 LangGraph。LangGraph 将负责编排状态、节点、条件分支和循环；它不会取代本课的 MCP Client。
