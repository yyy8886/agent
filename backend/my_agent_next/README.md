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

数据库只保存 API Key 对应的环境变量名。真实密钥放在 `backend/.env` 或部署平台的密钥管理中：

```dotenv
OPENAI_API_KEY=your-key
```

不要提交 `.env`，也不要把开发者密钥打包进发布产物。

## 启动

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
