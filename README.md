# AI 桌面助手：从命令行到 Electron

这是一个以学习为目的的渐进式项目。最终目标是亲手完成一个 **Electron + Python** 的跨平台 AI 桌面助手：Electron 负责界面、动画和系统交互，Python 负责模型、Agent、RAG、记忆和工具调用。

本仓库从课程示例逐步发展出了实验项目 `backend/my_agent_next`。课程仍然坚持由浅入深：前九课学习模型、消息、工具、MCP 和 LangGraph 基础；后续课程将这些知识组合成当前的 Agent 平台。每一课都遵循同一个节奏：

1. 先说明这一课只解决什么问题。
2. 你亲手创建或修改少量代码。
3. 运行并观察结果。
4. 解释代码为什么工作。
5. 完成小练习和验收，再进入下一课。

教学组织参考 [Agent Craft](https://github.com/yyy8886/agent-craft)：示例独立、逐级增加能力、强调可运行和理解原理。本项目会针对 Electron + Python 桌面架构重新编排内容，不照搬其代码。

## 最终架构

```text
Electron renderer (React)
        |
Electron main / preload
        |
HTTP + WebSocket (仅限 127.0.0.1，带临时 token)
        |
Python / FastAPI
        |
LangChain (模型、Prompt、Chain、简单 Agent)
        |
MCP (跨进程工具协议、Server、Client、权限)
        |
LangGraph (复杂决策、状态、循环、人工审批)
        |
LlamaIndex (文档、索引、检索) + SQLite
```

技术选择：

- 前端：Electron + React + Vite
- 后端：Python 3.11 或 3.12 + FastAPI + Uvicorn
- 基础 AI 能力：LangChain（DeepSeek 模型接入、Prompt、Chain、流式、简单 Agent）
- 工具协议：MCP（官方 Python SDK `FastMCP`、stdio/Streamable HTTP、Client 适配、权限）
- 复杂 Agent 编排：LangGraph（状态、节点、边、条件路由、循环、持久化、人工审批）
- 文档检索：LlamaIndex（加载、切分、索引、召回、来源引用）
- 流式通信：WebSocket
- 混合 RAG：将 LlamaIndex 检索器封装为 LangGraph 节点或工具
- 存储：SQLite；向量存储在 RAG 阶段再决定
- 打包：PyInstaller + electron-builder

> 选择原则：能用 LangChain 线性完成的任务，不引入 LangGraph；只有流程需要分支、循环、可恢复状态或人工审批时，才升级到 LangGraph。LlamaIndex 专注文档与检索，并可被封装成 LangChain 工具或 LangGraph 节点。

## 学习地图

| 阶段      | 课程                                                       | 产出                                     | 验收标准                           |
| --------- | ---------------------------------------------------------- | ---------------------------------------- | ---------------------------------- |
| 基础      | [01 环境与 DeepSeek 首次调用](backend/lecture/L1/README.md) | 命令行单轮问答                           | 输入“你好”能看到模型回复         |
| 基础      | [02 消息、提示词与参数](backend/lecture/L2/README.md)       | 有角色设定的问答                         | 能解释 system/user/assistant       |
| LangChain | [03 Prompt、Chain 与输出解析](backend/lecture/L3/README.md) | 结构清晰的问答链                         | 能解释链中每一环的输入输出         |
| LangChain | [04 对话记忆与流式输出](backend/lecture/L4/README.md)         | 命令行连续对话                           | 能记住名字并逐步输出 token         |
| LangChain | [05 简单 Agent 与工具调用](backend/lecture/L5/README.md)      | 时间工具                                 | 模型能选择并调用正确工具           |
| MCP       | [06 MCP Server 基础](backend/lecture/L6/README.md)          | 用 FastMCP 暴露一个工具                  | 能通过 stdio 启动并调用工具         |
| MCP       | [07 MCP Client 与 LangChain 适配](backend/lecture/L7/README.md) | 外部 MCP 工具接入 Agent              | 能连接、发现并执行 MCP 工具         |
| LangGraph | [08 为什么需要图](backend/lecture/L8/README.md)            | 第一个 `StateGraph`                      | 能判断任务是否真的需要 LangGraph   |
| LangGraph | [09 路由、循环与 Checkpointer](backend/lecture/L9/README.md) | 可恢复的复杂 Agent                    | 使用同一 thread id 可继续流程      |
| 检索      | [10 LlamaIndex 文档与索引](backend/lecture/L10/README.md)  | 可查询的本地索引                         | 能解释文档、Node、Embedding 与索引 |
| 检索      | [11 LlamaIndex 检索与引用](backend/lecture/L11/README.md)  | 带来源的文档问答                         | 能检查召回片段并核对引用           |
| 混合      | [12 LlamaIndex 接入 LangGraph](backend/lecture/L12/README.md) | 可决策是否检索的 RAG 图                | 普通闲聊不检索，文档问题才检索     |
| 服务      | [13 FastAPI 与分层架构](backend/lecture/L13/README.md)     | API、Service、Repository 最小项目         | 能解释每一层的职责                 |
| 服务      | [14 模型 API 管理与真实测速](backend/lecture/L14/README.md) | 多 provider 配置管理页面                  | 页面能调用真实模型并显示耗时       |
| Agent     | [15 Agent 配置与管理页面](backend/lecture/L15/README.md)   | 可配置人设、模型和启用状态的 Agent        | 刷新后 Agent 配置仍存在            |
| 对话      | [16 SQLite 会话、多轮历史与记忆](backend/lecture/L16/README.md) | 可恢复的单 Agent 多轮聊天              | 不同会话隔离且能记住用户信息       |
| 服务      | [17 SSE 聊天事件与 Web 控制台](backend/lecture/L17/README.md) | 单 Agent 对话页面                       | 页面持续显示回答和错误事件         |
| Tool      | [18 Tool Calling 循环与权限](backend/lecture/L18/README.md) | 模型—工具—模型循环与人工确认             | Tool 结果能交回模型形成最终回答    |
| Skill     | [19 SKILL.md、Loader 与 Agent 绑定](backend/lecture/L19/README.md) | 本地 Skill 系统                       | 能解释 Skill 与 Tool 的区别        |
| Skill     | [20 Skill 市场、安装与安全](backend/lecture/L20/README.md) | SkillsMP/ClawHub 搜索和安装               | 第三方 Skill 未授权时不能执行      |
| 绘图      | [21 draw.io Skill 与脚本资源](backend/lecture/L21/README.md) | 可编辑 `.drawio` 与预览图               | Agent 能找到脚本并完成验证         |
| LangGraph | [22 多 Agent 工作流与人工审批](backend/lecture/L22/README.md) | 分析、分派、执行、验证图                | 可观察状态、路由、循环和暂停       |
| 桌面      | [23 Electron 桌宠与后端进程](backend/lecture/L23/README.md) | Electron 管理 Python 服务                | 退出应用后无残留后端进程           |
| 工程      | [24 测试、打包与三端发布](backend/lecture/L24/README.md)   | Windows/macOS/Linux 安装包                | 干净机器可安装、运行、卸载         |

### 模型切换进阶内容安排

L1 只学习 YAML 选择模型和直白的 `if/elif`。更复杂的模型管理按依赖关系分散到后续课程：

| 课程              | 加入内容                                                 | 为什么放在这里                       |
| ----------------- | -------------------------------------------------------- | ------------------------------------ |
| L3 LangChain 基础 | `BaseChatModel`、薄 model factory、`init_chat_model` | 学会共同接口和 Chain 后再做抽象      |
| L5 工具调用       | 比较不同 provider 的工具调用、结构化输出和流式能力       | 客户端接口相似，但能力不一定完全相同 |
| L9 LangGraph      | 根据任务动态选择模型、复杂路由和人工确认                 | 这是流程决策，不是简单配置切换       |
| L13 FastAPI       | Pydantic 配置校验、统一错误、provider 生命周期           | 服务启动时需要可靠地验证配置和密钥   |
| L21 工程化        | LiteLLM/模型网关、fallback、限流、成本、监控             | 这些是生产运行与发布问题             |

学习原则：先看懂三个真实客户端，再抽象共同部分；先能手动切换，再学习自动路由和故障转移。

### MCP 两课的学习边界

MCP 放在 L5 工具调用之后、LangGraph 之前，因为它解决的是“工具如何以标准协议被发现和调用”，而 LangGraph 解决的是“复杂流程如何决策和循环”。

| 课程 | 只学习什么 | 暂时不学习什么 |
| --- | --- | --- |
| L6 MCP Server | FastMCP、tool/resource/prompt、stdio、输入 schema；只理解 HTTP 的用途 | 远程 MCP 部署、多 Agent 编排、Electron、复杂权限系统 |
| L7 MCP Client | 连接生命周期、工具发现、`langchain-mcp-adapters`、把 MCP 工具交给 Agent | 自己重新发明 MCP 协议、生产网关 |

L6 的验收是“外部客户端能调用我写的工具”；L7 的验收是“LangChain Agent 能发现并使用 MCP 工具”。通过这两课后，L8 才开始用 LangGraph 编排这些工具。

桌宠第一版只使用本地 `stdio` MCP：MCP Client 与 MCP Server 在同一台电脑上运行，不监听网络端口，也不要求用户部署服务器。远程 MCP 与第一版产品目标无关，不进入 L1-L21 主线。

### 完成主线后的可选进阶

以下内容在完成 L21、成功打包桌宠后再按需要学习，不影响主线项目验收：

| 可选专题 | 学习内容 | 适用场景 |
| --- | --- | --- |
| 远程 MCP Server | Streamable HTTP、远程 Client、连接与会话生命周期 | 多台设备共享同一套工具服务 |
| 远程 MCP 安全 | HTTPS、身份认证、权限、限流、日志脱敏、多用户隔离 | MCP Server 需要部署到局域网或公网 |
| MCP 服务运维 | 容器部署、健康检查、监控、升级和故障恢复 | 将 MCP 作为长期运行的生产服务 |

远程 MCP 不能只通过监听 `0.0.0.0` 暴露出去。必须同时设计身份认证、HTTPS、权限边界和用户数据隔离，因此它被独立为进阶专题。

## 项目将逐步长成这样

```text
agent/
├─ frontend/                 # 第 15 课开始创建
│  ├─ electron-main/
│  └─ renderer/
├─ backend/                  # 第 01 课开始创建
│  ├─ app/
│  └─ tests/
├─ shared/
│  └─ schema/                # 第 14 课定义通信事件
├─ docs/
└─ README.md
```

不要现在一次性创建全部目录。每一层都在它第一次有用途时创建。

## 学习约定

- 一次只进行一课，先验收再继续。
- 报错时粘贴完整错误文本，但删除 API Key、token 和个人路径中的敏感信息。
- 我会解释每条命令和关键代码，不会替你创建课程代码。
- 你可以要求提示，但建议先自己尝试；必要时我会从小提示逐步增加到完整答案。
- 从第 11 课开始，每个接口都会先定义契约和测试，再连接 Electron。

## 安全底线

- Python 服务只监听 `127.0.0.1`，不暴露到局域网。
- Electron 使用 `contextIsolation: true`，通过受控 preload API 通信。
- 应用启动时生成短期随机 token，HTTP/WebSocket 请求必须验证。
- 插件必须声明文件、网络和进程执行权限，默认拒绝。
- 外部工具调用必须设置超时，并限制输入、输出和可访问路径。
- 密钥只保存在后端安全存储中，不进入渲染进程。

## 参考资料

- [Agent Craft](https://github.com/yyy8886/agent-craft)
- [DeepSeek API 文档](https://api-docs.deepseek.com/)
- [OpenAI 模型文档](https://platform.openai.com/docs/models)
- [Ollama 文档](https://docs.ollama.com/)
- [LangChain Ollama 集成文档](https://docs.langchain.com/oss/python/integrations/chat/ollama)
- [LangGraph Python 文档](https://docs.langchain.com/oss/python/langgraph/overview)
- [LlamaIndex Python 文档](https://docs.llamaindex.ai/en/stable/)
- [LangChain 模型集成文档](https://docs.langchain.com/oss/python/integrations/chat/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Electron 安全指南](https://www.electronjs.org/docs/latest/tutorial/security)
