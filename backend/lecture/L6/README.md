# L6 MCP Server 基础与 VS Code 集成

L5 中，工具直接写在 Agent 所在的 Python 进程里：

```text
Agent Python 进程
  ├─ 模型
  └─ get_current_time() 工具
```

这样简单，但工具和 Agent 绑定在一起。L6 使用 MCP（Model Context Protocol）把工具单独变成一个服务：

```text
MCP Client / Host
        │ MCP 协议
        ▼
MCP Server
  ├─ get_current_time
  ├─ read_note
  └─ 其他受控能力
```

## MCP Server 是干什么的

MCP Server 是一个遵守 MCP 协议的程序。它向外声明三类能力：

- **Tools**：模型可以请求执行的函数，例如查时间、查询数据库。
- **Resources**：客户端可以读取的上下文资源，例如文档或项目文件。
- **Prompts**：可复用的提示词模板。

MCP Server 不负责决定什么时候调用工具，也不负责最终回答用户。它负责：

1. 声明能力和输入 schema。
2. 接收 MCP Client 的请求。
3. 校验参数并执行受控逻辑。
4. 返回结构化结果。

## VS Code 扩展里的 MCP Server 是什么

VS Code 本身可以作为 MCP Host/Client。安装支持 MCP 的扩展（例如 Copilot Chat 后），你可以在 VS Code 中配置 MCP Server，让扩展里的 Agent 使用它提供的工具。

```text
VS Code Chat / Agent 模式
        │ 充当 MCP Host/Client
        ▼
你配置的 MCP Server
        ├─ 本地 Python 进程（stdio）
        ├─ Node.js 进程（stdio）
        └─ 远程 HTTP MCP 服务
```

它的用途是：

- 在 VS Code 对话中调用项目工具。
- 让 Agent 查询数据库、读取文档或运行受控检查。
- 调试你自己写的 MCP Server，先不接入 Electron。
- 把同一个 MCP Server 复用于 VS Code、LangChain Client 和其他 MCP Host。

VS Code **不是** MCP Server 本身。通常它是 MCP Host；你配置的 Python/Node 程序才是 MCP Server。VS Code 扩展负责连接、展示工具并把用户批准结果传给 Server。

### VS Code 配置文件

项目级配置通常放在：

```text
.vscode/mcp.json
```

一个 stdio Server 的示意配置：

```json
{
  "servers": {
    "lesson-tools": {
      "type": "stdio",
      "command": "python",
      "args": [
        "${workspaceFolder}/backend/lecture/L6/mcp_server.py"
      ]
    }
  }
}
```

含义：

- `lesson-tools`：VS Code 中显示的 Server 名称。
- `type: stdio`：VS Code 启动子进程，通过标准输入/输出通信。
- `command`：启动 MCP Server 的命令。
- `args`：传给程序的参数。
- `${workspaceFolder}`：当前 VS Code 工作区路径变量。

Windows 项目中更可靠的做法通常是指定虚拟环境解释器的绝对路径，或让启动脚本负责激活正确环境。不要把 API Key 直接写进 `mcp.json`。

## stdio 与 HTTP

### stdio

```text
VS Code 启动 Python 子进程
  -> stdin/stdout 传输 MCP 消息
  -> VS Code 关闭时结束子进程
```

优点是本地、简单、无需端口；缺点是每个 Host 可能启动一个独立进程。

### Streamable HTTP

```text
MCP Client -> HTTP -> 正在运行的 MCP Server
```

适合共享服务、远程服务和需要独立生命周期的场景，但必须额外处理鉴权、网络暴露和并发。

L6 先学习 stdio。HTTP MCP Server 放到后续服务课程。

## 本课学习路线

1. 检查 Python MCP 依赖。
2. 用官方 MCP 1.29 `FastMCP` 写一个 `get_current_time` 工具。
3. 通过 stdio 启动并测试 Server。
4. 在 VS Code 的 `mcp.json` 中注册它。
5. 在 VS Code Agent 对话中观察工具发现和调用。
6. 学习 MCP Server 的权限边界和日志规则。

## 检查点 1：确认 VS Code 能使用 MCP

先确认：

- VS Code 已更新到支持 MCP 的版本。
- 已安装你计划使用的 MCP Host/Agent 扩展。
- 当前打开的是项目根目录 `C:\Users\yanzichen\Desktop\agent`。
- 你能在扩展的 Agent/Chat 模式中看到 MCP Server 管理入口。

VS Code 的 MCP 支持属于 Host 能力，不影响我们后端的 Python 虚拟环境。L6 的 Server 代码仍然放在 `backend/lecture/L6`。

## 检查点 2：理解安全边界

VS Code 连接 MCP Server 后，扩展里的 Agent 可能会请求调用它的工具。因此：

- 工具默认只提供无副作用操作。
- 写文件、删除文件、执行命令必须单独设计和授权。
- 不把 `.env`、API Key 和整个用户目录暴露为资源。
- stdio Server 的 stdout 不能混入普通调试日志，否则会破坏协议消息。
- 调试日志写 stderr 或文件。

MCP 是通信协议，不是沙箱。Server 自己必须校验参数和权限。

## VS Code 和我们最终应用的关系

```text
现在：VS Code 作为 MCP Host，帮助我们调试 Server

后续：Python Agent 作为 MCP Client，连接外部工具

最终：Electron + FastAPI + LangGraph 作为产品，按权限使用 MCP 工具
```

用 VS Code 先调通 Server 的好处是，可以把“协议连接问题”和“桌面应用问题”分开排查。

## L6 验收目标

- [ ] 能解释 MCP Server、MCP Client 和 MCP Host 的区别。
- [ ] 能说明 Tool、Resource、Prompt 的区别。
- [ ] 能解释 VS Code 扩展为什么是 Host，而不是你写的 Server。
- [ ] 能说出 stdio 和 Streamable HTTP 的差异。
- [ ] 能指出为什么 stdout 不能随便打印调试日志。

完成概念验收后，再创建 `mcp_server.py`，进入第一个 FastMCP 工具练习。不要先注册一个不存在的 Server 配置。

## MCP SDK 版本说明

本课程统一使用官方 Python SDK `mcp 1.29`：

```python
from mcp.server.fastmcp import FastMCP
```

选择 1.29 是因为当前课程使用的 `langchain-mcp-adapters 0.3.2` 明确要求：

```text
mcp >= 1.24.0, < 2.0.0
```

MCP 2.x 使用重新设计的 `MCPServer` API，但目前不能与该适配器安装在同一个 Python 环境中。SDK 主版本不等于 MCP 协议版本；使用 1.29 不影响 Inspector、VS Code MCP，以及 Tool、Resource、Prompt 的学习。

等 LangChain 适配器正式支持 MCP 2.x 后，再统一升级。不要在当前虚拟环境中强制安装 `mcp>=2`，否则 pip 会产生依赖冲突或使 L7 无法工作。

## 检查点 3：编写第一个 MCP Server

在 `mcp_server.py` 中写入：

```python
from datetime import datetime

from mcp.server.fastmcp import FastMCP


server = FastMCP(
    name="lesson-tools",
    instructions="提供 L6 课程中的低风险本地工具。",
)


@server.tool()
def get_current_time() -> str:
    """返回当前电脑所在时区的日期、时间和时区偏移。"""
    now = datetime.now().astimezone()
    return now.isoformat(timespec="seconds")


if __name__ == "__main__":
    server.run(transport="stdio")
```

逐段理解：

- `FastMCP(...)`：创建一个 MCP Server，不会立即启动。
- `@server.tool()`：把普通 Python 函数注册为 MCP Tool。
- docstring：会成为工具描述，帮助 Client/模型判断何时使用。
- 返回类型 `str`：参与生成工具输出 schema。
- `server.run(transport="stdio")`：通过标准输入/输出与 Host 通信。

先只检查语法：

```powershell
python -m py_compile lecture\L6\mcp_server.py
```

不要直接用 `python lecture\L6\mcp_server.py` 判断成功与否。stdio Server 启动后会等待 Host 发送协议消息，终端没有普通输出是正常现象。

### 为什么不能在 stdout 打印日志

stdio 模式把 stdout 当作协议通道。下面这种调试代码可能破坏 MCP 消息：

```python
print("Server 启动了")
```

需要调试时使用 stderr 或日志文件，例如：

```python
import sys

print("调试信息", file=sys.stderr)
```

当前最小 Server 不添加调试日志。

## 检查点 4：使用 MCP Inspector 测试

官方 MCP CLI 已随 `mcp[cli]` 安装。先查看版本：

```powershell
mcp version
```

从 `backend` 目录启动 Inspector：

```powershell
mcp dev lecture\L6\mcp_server.py:server
```

这里的格式是：

```text
Python 文件路径:FastMCP 对象名
```

我们的对象名是：

```python
server = FastMCP(...)
```

Inspector 启动后，在界面中：

1. 连接 Server。
2. 打开 Tools 列表。
3. 找到 `get_current_time`。
4. 不传参数调用它。
5. 确认返回带时区偏移的 ISO 时间。

停止 Inspector 时回到终端按 `Ctrl+C`。

如果系统提示找不到 Node/npm，说明 Inspector 的前端运行环境未准备好；MCP Server 本身仍可能正确。安装 Node.js 后重试，或下一课使用 Python Client 测试。

### Windows：`npx not found`

MCP Inspector 的网页界面通过 Node.js 工具启动。依次检查：

```powershell
node --version
npm --version
npx --version
```

如果命令不存在，安装 Node.js 当前 LTS 版本。Windows 可使用官方安装程序，或执行：

```powershell
winget install OpenJS.NodeJS.LTS
```

安装后关闭并重新打开 PowerShell，让 PATH 重新加载；再激活 Python 虚拟环境：

```powershell
Set-Location C:\Users\yanzichen\Desktop\agent\backend
.\.venv\Scripts\Activate.ps1
```

确认 `npx --version` 成功后重新运行：

```powershell
mcp dev lecture\L6\mcp_server.py:server
```

Node.js 是 Inspector 和后续 Electron 的开发依赖，不会替代 Python MCP Server。

## MCP Inspector 界面导览

### Servers

用于查看 MCP Server 的连接与启动信息：

- 是否已连接。
- 使用 stdio 还是 HTTP。
- 实际启动命令。
- MCP 协议版本。
- 开启或关闭当前连接。

`Read-only session` 表示本次 Server 由 `mcp dev` 临时启动，不能在网页里永久修改启动配置；不影响调用工具。

### Tools

用于发现和手动执行 Server 暴露的工具：

1. Inspector 发送 `tools/list`。
2. 左侧显示工具名称。
3. 点击工具查看描述和参数 schema。
4. 点击 Run Tool，Inspector 发送 `tools/call`。
5. 右侧显示结构化结果或错误。

当前 Server 只有 `get_current_time`，所以列表中只有一个工具。

### Prompts

用于查看 Server 提供的可复用提示模板：

- `prompts/list`：列出模板。
- `prompts/get`：传入模板参数并取得生成后的消息。

当前为空，因为还没有使用 `@server.prompt()` 注册 Prompt。Prompt 不会自己调用模型，它只生成一组可供 Host 使用的消息。

### Resources

用于查看和读取 Server 暴露的上下文资源：

- `resources/list`：列出静态资源。
- `resources/templates/list`：列出带参数的资源模板。
- `resources/read`：读取指定 URI 的内容。

当前为空，因为还没有使用 `@server.resource(...)` 注册 Resource。Resource 适合只读文档和结构化数据，不等同于执行动作的 Tool。

### Protocol

用于观察 MCP 请求与响应。你截图中的记录含义：

| 记录                            | 含义                                 |
| ------------------------------- | ------------------------------------ |
| `TOOLS/LIST`                  | Client 询问 Server 有哪些工具        |
| `TOOLS/CALL get_current_time` | Client 请求执行时间工具              |
| `PROMPTS/LIST`                | Client 询问有哪些 Prompt，目前为空   |
| `RESOURCES/LIST`              | Client 询问有哪些 Resource，目前为空 |

`CLIENT -> SERVER` 表示请求方向，`OK` 表示成功，毫秒数字表示耗时。展开单条记录可检查请求参数、结果或错误。

常见操作：

- **Newest First**：切换时间排序。
- **Clear**：只清空当前 Inspector 中的显示记录，不删除 Server 数据。
- **Export**：导出协议记录，方便排错或分享脱敏后的日志。
- 单条记录的回转箭头：重新发送该请求。
- 图钉：固定重要记录，便于比较。
- 展开按钮：查看完整请求和响应。

### Console

用于查看 Inspector、连接过程和 Server stderr 日志。stdio Server 的正常协议数据走 stdout，调试日志应走 stderr，因此这里是排查启动失败和异常的主要位置。

### 推荐调试顺序

```text
Servers：先确认 Connected
  -> Tools/Prompts/Resources：确认能力能被发现
  -> 手动调用或读取
  -> Protocol：检查具体请求和响应
  -> Console：检查启动和运行错误
```

不要把包含 API Key、token、用户文件内容的 Export 日志直接公开。

## 检查点 5：理解初始化握手

Inspector 建立连接时会出现：

```text
INITIALIZE
  -> Server 返回名称、版本、协议版本和能力
NOTIFICATIONS/INITIALIZED
  -> Client 通知 Server：初始化完成
TOOLS/LIST、PROMPTS/LIST、RESOURCES/LIST
  -> Client 自动发现 Server 提供的能力
```

`INITIALIZE` 第一次耗时可能较长，因为 MCP 子进程、Python 环境和 Inspector 正在启动；后续 list/call 通常更快。

## 检查点 6：添加 Prompt 与 Resource

先在运行 Inspector 的终端按 `Ctrl+C`。然后在 `mcp_server.py` 中、`if __name__ == "__main__":` 之前增加：

```python
@server.prompt(
    name="python_teacher",
    description="生成一个用于讲解 Python 主题的用户提示词。",
)
def python_teacher(topic: str) -> str:
    """根据主题生成教学提示词。"""
    return (
        f"请使用简体中文讲解 Python 的 {topic}。"
        "先解释概念，再给一个简短例子，最后列出一个常见错误。"
    )


@server.resource(
    "lesson://overview",
    name="l6_overview",
    description="L6 课程的只读简介。",
    mime_type="text/plain",
)
def get_l6_overview() -> str:
    """返回 L6 课程简介。"""
    return (
        "L6 学习 MCP Server：Tool 用于执行动作，"
        "Resource 用于读取内容，Prompt 用于生成消息模板。"
    )
```

三者区别：

```text
Tool：执行函数并返回结果
Prompt：接收参数，生成可复用提示消息
Resource：通过 URI 提供只读内容
```

### Tool、Resource、Prompt 的关系与区别

它们都是 MCP Server 向 Client 声明的能力，但语义不同：

```text
Tool：帮我做一件事
Resource：给我一份资料
Prompt：告诉我应该怎样提问
```

| 类型     | 核心作用               | 是否执行动作 | 当前示例                  |
| -------- | ---------------------- | ------------ | ------------------------- |
| Tool     | 执行函数并返回实时结果 | 是           | `get_current_time`      |
| Resource | 通过 URI 提供内容      | 通常只读     | `lesson://overview`     |
| Prompt   | 根据参数生成提示消息   | 否           | `python_teacher(topic)` |

Tool 调用链：

```text
Client 请求 tools/call
  -> Server 执行 Python 函数
  -> 返回工具结果
```

Resource 读取链：

```text
Client 请求 resources/read + URI
  -> Server读取或生成内容
  -> 返回文本、JSON 或二进制内容
```

Prompt 获取链：

```text
Client 请求 prompts/get + 参数
  -> Server 生成提示消息
  -> Host 决定是否把它发送给模型
```

Prompt 本身不会调用模型，Resource 本身不会自动进入模型上下文，Tool 也不是模型亲自执行。MCP Host/Agent 决定如何使用 Server 提供的能力。

三者可以组合：

```text
Prompt：生成“代码审查员”的检查要求
  -> Resource：读取项目编码规范
  -> 模型分析代码
  -> Tool：查询实时信息或执行受控检查
  -> 模型生成最终回答
```

选择规则：

```text
需要执行动作或获取实时结果 -> Tool
需要读取一份有 URI 的内容  -> Resource
需要复用一套提问模板       -> Prompt
```

检查语法并重启：

```powershell
python -m py_compile lecture\L6\mcp_server.py
mcp dev lecture\L6\mcp_server.py:server
```

在 Inspector 中：

1. `Prompts` -> 选择 `python_teacher` -> topic 输入 `列表` -> Get Prompt。
2. `Resources` -> 选择 `lesson://overview` -> Read Resource。
3. `Protocol` -> 观察新增的 `prompts/get` 与 `resources/read`。

Prompt 的返回值不会自动发送给大模型；Inspector 只是展示生成后的消息。Resource 也只提供内容，不会执行 Agent 流程。

## 检查点 7：在 VS Code 中注册 MCP Server

Inspector 测试通过后，在项目根目录创建：

```text
C:\Users\yanzichen\Desktop\agent\.vscode\mcp.json
```

内容：

```json
{
  "servers": {
    "lesson-tools": {
      "type": "stdio",
      "command": "${workspaceFolder}/backend/.venv/Scripts/python.exe",
      "args": [
        "${workspaceFolder}/backend/lecture/L6/mcp_server.py"
      ]
    }
  }
}
```

为什么使用虚拟环境解释器的明确路径？VS Code 启动 MCP Server 时不会自动继承你在另一个终端激活的 `.venv`。明确指定后才能找到 `mcp` 包。

操作步骤：

1. 在 VS Code 中打开项目根目录 `agent`，不是只打开 `backend`。
2. 创建并保存 `.vscode/mcp.json`。
3. 打开 VS Code 的 MCP Server 管理入口。
4. 启动或刷新 `lesson-tools`。
5. 检查工具列表是否出现 `get_current_time`。
6. 在支持 MCP 的 Agent 模式中请求“调用工具查询当前时间”。

VS Code 可能先要求你信任 Server 或确认工具调用。先检查工具名称和参数，再批准。

`.vscode/mcp.json` 只保存启动配置，不包含 MCP 工具代码。不要在其中写 API Key；需要秘密时使用安全输入、环境配置或系统凭据库。
