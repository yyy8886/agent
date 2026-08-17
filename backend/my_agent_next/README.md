# My Agent Next

`My Agent Next` 是一个可本地运行的多 Agent 应用后端。当前稳定版本已经打通“模型配置 -> Agent -> Skill -> Tool -> 记忆 -> 对话 -> LangGraph 工作流”的完整链路，并提供浏览器工作台进行配置和运行。

## 当前能力

- 管理 OpenAI、DeepSeek、Ollama 和 OpenAI 兼容服务，支持真实模型测速。
- 创建 Agent，配置人设、模型和绑定的 Skill。
- Agent 多轮对话、原生流式输出、工具调用轨迹、会话恢复和手动停止。
- SQLite 持久化 API 配置、Agent、对话、消息、用户记忆和 Skill 兼容性结果。
- 创建、安装、卸载和自动绑定 Skill；通过 `skills/index.json` 保存轻量索引。
- 从 SkillsMP、ClawHub 和 GitHub 预览、安装 Skill，并以绿、黄、红显示兼容程度。
- 手动修改 `SKILL.md` 后，根据 SHA-256 内容指纹自动刷新索引和兼容性状态。
- 在 Windows 和 Linux 上按当前运行平台选择命令与 Skill 脚本入口。
- 直接保存并执行用户编写的 LangGraph Python 工作流。
- 工作流支持条件边、回边循环、Agent、Tool、Skill、子工作流和自定义运行事件。
- 工作流在独立 Worker 进程中运行，支持超时、递归限制、软取消和强制终止。
- 工作流对话及最终回答持久化，刷新页面后可以继续查看。

尚未完成的方向包括低权限或容器级 Worker 隔离、工作流版本发布与回滚、运行轨迹持久化、可视化工作流编辑器、LlamaIndex 知识库和 Electron 桌面端。

## 技术栈

| 技术 | 用途 |
| --- | --- |
| Python 3.11 / 3.12 | 后端与 Worker 运行环境 |
| FastAPI + Uvicorn | HTTP API、静态页面和 SSE |
| HTML + CSS + JavaScript | Web 工作台 |
| LangChain | 模型接口、消息和 Tool Calling |
| LangGraph | 代码优先工作流、条件和循环 |
| SQLite | 应用持久化数据 |
| httpx | 网页读取和 Skill 市场请求 |
| YAML | 应用配置及 Skill 执行清单 |

## 分层和运行边界

```text
浏览器工作台
    | HTTP / SSE
FastAPI API
    | Service
Repository --------> SQLite
    |
工作流运行管理器 ---> 独立 Worker ---> LangGraph / Agent / Tool / Skill
```

- API 层处理请求、响应和 SSE 连接。
- Service 负责业务编排，Repository 负责 SQLite 读写。
- 普通 Agent 对话在聊天服务中执行，Agent 和工作流共用上下文装配逻辑。
- 用户工作流源码不会在 FastAPI 进程中执行，而是生成不可变运行产物后由独立 Worker 导入运行。
- `WorkflowRuntime` 是工作流访问 Agent、Tool、Skill 和已声明子工作流的唯一公开入口。

## 目录结构

```text
my_agent_next/
|- app/
|  |- workflows/                 # 工作流契约、存储、产物、Worker 和运行管理
|  |- tools/                     # Agent 和工作流可调用的 Tool
|  |- static/index.html          # Web 工作台
|  |- *_repository.py            # SQLite Repository
|  |- *_service.py               # 业务服务
|  `- web_server.py              # FastAPI 入口
|- skills/
|  |- index.json                 # Skill 轻量持久化索引
|  |- _loader.py                 # Skill 发现、指纹校验和按需加载
|  `- <skill-name>/              # SKILL.md、scripts、references 等资源
|- data/app.db                   # 默认 SQLite 数据库
|- tests/                        # 自动测试
|- workflow_sdk.py               # 用户工作流允许导入的稳定接口
`- config.yaml                   # 服务和聊天参数
```

所有项目资源路径均根据包或配置文件位置解析，不依赖当前工作目录，也不写死开发机器的绝对路径。

## Agent 对话流程

```text
用户发送消息
-> 读取 Agent、人设、模型、绑定 Skill、记忆和历史
-> 模型原生流式生成
-> 如有 Tool Call，执行权限检查并调用 Tool
-> Tool 结果交还模型继续生成
-> SSE 实时发送文本和调用轨迹
-> 保存用户消息与最终回答
```

切换到市场或 API 配置页面不会销毁正在进行的 SSE 对话。工作台的停止按钮会取消当前 Agent 任务，最大工具循环次数由 `config.yaml` 控制。

## Skill 机制

每个 Skill 是 `skills/<skill-name>/` 下的独立目录，`SKILL.md` 是内容真源。`skills/index.json` 只保存名称、描述、目录和 SHA-256 指纹，正文在需要时按 Agent 绑定关系加载，不会把所有 Skill 一次性加入模型上下文。

Agent 创建 Skill 后，应用会将它写入项目 Skill 目录、刷新索引，并自动绑定给发起创建的 Agent。手动修改 Skill 后，加载器会根据指纹发现变化。市场安装和手动重新扫描会写入兼容性等级、分数、问题和扫描时间。

可执行 Skill 可以用 `execution.yaml` 声明参数、超时，以及 Windows PowerShell 和 Linux/macOS Bash 入口。外部 Skill 和脚本属于不可信输入，执行仍需遵守应用权限设置。

## MCP 服务

工作台在顶部导航的“Skill 市场”右侧提供并列、独立的“MCP 服务”页面，导航顺序固定为
“Skill 市场” -> “MCP 服务”。课程 L6 中通过
`mcp dev lecture\L6\mcp_server.py:server` 打开的网页是 MCP Inspector；新页面参考它的
连接、能力发现和手动调用体验，但不会直接嵌入 Inspector。Inspector 继续作为开发者的
外部诊断工具，应用页面负责持久化配置、权限控制、Agent 绑定和运行轨迹。

### 产品边界

- Skill 是项目内的知识与工作流目录，`SKILL.md` 是内容真源；它告诉 Agent 应该怎样完成任务。
- MCP Server 是独立进程或远程服务，通过标准协议提供 Tool、Resource 和 Prompt；它提供可以实际调用的外部能力。
- Agent 可以同时绑定 Skill 和 MCP Server。两者并不冲突：Skill 可以指导 Agent 何时调用 MCP 工具，但绑定关系和权限必须分别管理。
- 第一阶段只支持本地 `stdio`，待生命周期、权限和日志稳定后再加入 Streamable HTTP。

### 传输方式与部署定位

| 方式 | 连接形态 | 适用场景 | 当前状态 |
| --- | --- | --- | --- |
| `stdio` | 应用按配置启动本机 MCP 子进程，通过标准输入输出通信 | 本地开发、单机工具、随应用一起部署的 Python/Node 服务 | 已支持 |
| Streamable HTTP | 应用通过 URL 连接持续运行的标准 MCP Server | Linux/Docker 部署、跨机器调用、多个 Agent 或应用共享服务 | 计划支持 |

Streamable HTTP 不会替换 `stdio`，两种方式将共用 MCP Service、Agent 授权、能力展示和工作流节点接口。引入它以后，MCP Server 可以独立部署、升级和扩缩容；Windows 上的应用也可以调用 Linux 上的服务，并通过统一的健康检查、日志、监控、限流和重试进行运维。持续运行的服务还可以避免每次调用都启动本地子进程的开销。

远程连接同时扩大了安全边界。正式启用前必须完成 HTTPS、Token 或 Header 认证、允许地址策略和 SSRF 防护，并限制重定向、内网地址及响应大小；还需要处理连接超时、断线重连、租户权限和敏感日志脱敏。服务 URL 与认证配置可以持久化，但数据库仍只保存密钥对应的环境变量名，不保存密钥原文。

### 页面结构

“MCP 服务”主页使用紧凑列表展示每个 Server 的名称、传输方式、连接状态、能力数量、
最近检查时间和已绑定 Agent。展开单个 Server 后提供以下标签页：

| 标签页 | 作用 |
| --- | --- |
| 概览 | 查看启动命令或 URL、环境变量名、工作目录、协议版本和 Server 能力声明 |
| Tools | 执行 `tools/list`，根据输入 schema 生成表单，手动发送 `tools/call` 并查看结构化结果 |
| Resources | 查看资源 URI、MIME 类型并手动执行 `resources/read` |
| Prompts | 查看参数 schema，执行 `prompts/get` 并预览生成的消息，但不自动发送给模型 |
| 协议日志 | 按时间展示 initialize、list、call/read/get 的方向、耗时、结果和错误，可重试与复制脱敏报告 |
| Agent / 工作流绑定 | 控制哪些 Agent 可以发现该 Server，以及哪些 MCP 能力可以作为工作流节点使用 |

页面顶部提供“添加服务”和“重新检查”操作。新增本地服务时填写名称、Python/Node 命令、
参数、工作目录和环境变量名；密钥只引用环境变量，不在页面、数据库或日志中显示真实值。
连接测试必须依次完成：启动进程、`initialize`、能力列表读取、一次可选的手动调用、正常关闭。

### 后端边界

```text
MCP 页面 / Agent / Workflow
          |
      MCP Service
          |
  MCP Connection Manager
      |             |
 local stdio   Streamable HTTP（后续）
          |
      MCP Server
```

- API 只处理配置请求、测试请求和流式事件，不直接维护 MCP 子进程。
- MCP Service 负责校验配置、权限和调用策略。
- Connection Manager 统一管理启动、握手、能力发现、超时、重连和关闭，避免每次 Tool Call 都创建无主子进程。
- Agent 与工作流通过统一 MCP Gateway 调用能力，不直接访问连接对象；工作流提供显式 MCP 节点，节点配置固定的 Server、Tool、输入映射和输出字段。
- SQLite 计划保存 Server 配置、Agent 绑定和最近一次能力快照；实时连接、进程句柄和未脱敏调用内容不写入数据库。
- MCP 工具转换为模型 Tool 时保留来源标识，例如 `mcp:<server-id>:<tool-name>`，避免与本地 Tool 重名，也便于前端展示调用来源。

### 实现状态

1. 已完成本地 stdio Server 的增删改查、连接检查和 Inspector 式 Tools/Resources/Prompts 手动测试。
2. 已完成 Agent 绑定与工具级来源前缀，普通对话和工作流 Agent 可以发现并调用已授权 MCP Tool。
3. 已完成可视化工作流 MCP 独立节点、SSE 输入输出轨迹、超时传递和 stdio 子进程自动回收。
4. 下一阶段将按 MCP 标准增加 Streamable HTTP，而不是自定义 REST 工具协议；同时补充 HTTPS、认证、地址白名单与 SSRF 防护、限流、重连和多用户隔离。在这些安全能力完成前不允许配置任意公网地址或将服务直接暴露到公网。

第一阶段的验收标准是：用户能在页面添加 L6 的时间 Server，看到 `get_current_time` 的
schema，手动调用成功并查看完整握手与调用轨迹；将该 MCP Server 绑定给指定 Agent 后，
普通 Agent 对话能够发现并实际调用 `get_current_time`；工作流中的 Agent 节点也能发现并
调用同一个 MCP 工具。此外，用户能够把 `get_current_time` 作为独立 MCP 节点加入可视化
工作流，不经过 Agent 直接执行，并将结果写入后续节点可引用的状态字段。两种工作流调用
方式都必须在节点轨迹中显示 MCP 来源、参数、结果、耗时和错误；参数映射失败、调用超时
和用户停止也要得到明确的节点状态。停止对话、停止工作流或退出应用后均不得残留 MCP 子进程。

## LangGraph 工作流

工作流编辑器保存的是可直接运行的 LangGraph Python 源码，不会把源码转换为自定义节点格式。保存前的 AST 静态验证只检查语法、入口、导入和明显危险调用；验证通过不等于安全沙箱。

每个工作流必须提供无参数同步入口：

```python
def build_workflow():
    return graph.compile()
```

界面输入至少包含：

```json
{"message": "用户输入"}
```

最终状态必须提供可显示的：

```json
{"answer": "最终回答"}
```

节点通过 `Runtime[WorkflowRuntime]` 调用应用能力：

```python
await runtime.context.call_agent("mabel", {"message": state["message"]})
await runtime.context.call_tool("tool-name", {"value": "..."})
await runtime.context.call_skill("weather-skill", {"city": "上海"})
await runtime.context.call_workflow("declared_dependency", {"message": "..."})
```

子工作流必须先在编辑器中声明依赖键。发布产物会把依赖键固定到目标工作流版本，源码不能在运行时任意选择子工作流。原生 `add_conditional_edges()`、回边循环和节点内部的 `if`、`for`、`while` 均可使用，但循环必须有业务退出条件；应用的递归限制、总超时和停止按钮是最后保护。

运行时通过 SSE 展示节点输入输出、Agent 调用、工具调用、Skill 调用、子工作流和最终结果。最终回答显示在上方，完整轨迹在结束后自动折叠。

更完整的代码契约见 [app/workflows/README.md](app/workflows/README.md)，编辑器中也可以点击“工作流配置”旁的问号查看逐句示例。

## 数据与密钥

默认持久化文件为 `data/app.db`，主要保存：

- `api_profiles`：模型供应商、模型名、Base URL、API Key 环境变量名和默认配置。
- `agents`：Agent 人设、模型与 Skill 绑定。
- `chat_threads`、`chat_messages`：Agent 和工作流对话。
- `user_memories`：长期用户记忆。
- `skill_compatibility`：Skill 兼容性扫描结果和内容指纹。
- `mcp_servers`：MCP Server 的传输方式、启动命令、参数、相对工作目录、环境变量名和启用状态。
- `mcp_agent_bindings`：Agent 与 MCP Server 的授权绑定；不保存连接对象、进程句柄或环境变量真实值。

数据库只保存 API Key 对应的环境变量名。真实密钥放在 `backend/.env` 或部署平台的密钥管理中：

```dotenv
OPENAI_API_KEY=your-key
```

不要提交 `.env`，也不要把开发者密钥打包进发布产物。

## 启动

### Electron 桌面工作台

桌面版采用“Electron 内置浏览器工作台 + FastAPI + Python Worker”架构。Electron 只负责窗口、后端生命周期和外部链接；Agent、Skill、MCP、工作流与 SQLite 仍由 FastAPI 管理。

```powershell
cd desktop
npm install
npm start
```

启动器会在 Windows 优先选择 `backend/.venv/Scripts/python.exe`，在 Linux 优先选择 `backend/.venv-linux/bin/python`，也可以通过 `MY_AGENT_PYTHON` 指定解释器。它会选择随机的本机端口、启动 FastAPI、等待 `/api/health` 就绪后显示窗口，并在应用退出时回收整个后端进程树。

桌面页面启用 `contextIsolation` 和 Chromium 沙箱，关闭 `nodeIntegration`。数据库、`.env`、用户 Skill 和工作流属于可写持久化数据，不进入 Electron 的 `app.asar`。当前第一阶段打包仍要求目标机器具备兼容的 Python 环境；内置 Python Runtime 属于下一阶段。

Windows PowerShell：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m my_agent_next.app.web_server
```

Linux：

```bash
cd backend
source .venv/bin/activate
python -m my_agent_next.app.web_server
```

默认地址为 `http://127.0.0.1:19845`，实际主机和端口以 `my_agent_next/config.yaml` 为准。不要同时启动多个服务器入口占用同一端口。

## 验证

在 `backend` 目录和项目虚拟环境中运行：

```powershell
python -m unittest discover -s my_agent_next/tests -p "test_*.py"
```

工作流相关测试覆盖源码契约、条件和循环、直接 Worker 执行、嵌套调用、事件、会话持久化、取消及强制终止。

## 安全注意事项

- Tool 调用默认需要用户确认，命令、网络、安装和删除操作尤其如此。
- 市场 Skill、网页内容和用户工作流源码均视为不可信输入。
- 静态检查不是执行隔离；正式对外部署前仍需给 Worker 增加低权限用户或容器沙箱。
- 工作流必须通过公开 SDK 调用应用能力，不能直接访问 Repository、API Key 或宿主内部对象。
- 为条件和循环设置明确停止条件，不要只依赖 LangGraph 递归上限。
