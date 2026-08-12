# my_agent_next

这是桌面 Agent 的重新设计版本，按可验证的小步骤构建。

当前完成范围：**模型 API 配置管理后端、API 管理页面和真实模型测速**。暂时没有 Agent、工作流、Skill 或聊天。

## 当前结构

```text
my_agent_next/
├─ app/
│  ├─ api_profile.py
│  ├─ api_profile_repository.py
│  ├─ api_profile_service.py
│  ├─ web_server.py
│  └─ static/
│     └─ index.html
├─ data/
│  └─ app.db                  # 首次运行自动创建，不提交密钥
├─ scripts/
│  └─ seed_api_profiles.py
└─ tests/
   └─ test_api_profile_service.py
```

API Profile 管理的是模型连接配置，不是 HTTP 路由：

- 显示名称与唯一 ID
- provider：`openai`、`deepseek`、`ollama`
- 模型名称和 base URL
- temperature、timeout、max retries
- API Key 的环境变量名称
- 是否启用、是否为默认配置

API Key 本身只存放在 `.env` 或操作系统安全存储中，不进入 SQLite，也不会由管理层返回。

## 开发原则

- 一次只完成一个阶段，验证通过后停止，等待确认再继续。
- 页面只负责显示和用户操作，不直接读写 SQLite，也不包含 Agent 业务逻辑。
- HTTP 接口负责接收请求，Service 负责业务规则，Repository 负责数据库读写。
- API Key 不写入数据库、配置页面、日志或 Git，只记录对应的环境变量名称。
- 每个阶段都需要最小可运行示例和自动测试；模型测速必须额外调用真实模型验证。
- 优先复用课程中已经学习的 LangChain、LangGraph、MCP、多轮对话和状态保存方式。

## 开发计划

### 阶段 1：API 管理后端（已完成）

- 用 SQLite 保存 OpenAI、DeepSeek、Ollama 和 OpenAI 兼容接口的连接配置。
- 支持新增、查询、修改、删除、启用和设置默认配置。
- 保存模型名称、Base URL、temperature、timeout 和重试次数。
- 数据库只保存 API Key 的环境变量名称。

验收标准：CRUD 测试通过；任意时刻最多只有一个默认 API 配置。

### 阶段 2：API 管理页面与真实测速（已完成，等待页面验收）

- 在 Web 页面查看和编辑 API 配置。
- 点击“测速”后，使用该配置调用真实模型。
- 向模型发送简短问候，并显示完整响应耗时、回答预览或错误。
- 页面调用 HTTP API，不直接操作数据库。

验收标准：至少选择一个已配置 API，在页面完成一次真实测速并得到模型回答。

### 阶段 3：Agent 管理后端

- 定义 Agent 的名称、身份、人设提示词、职责、使用的 API 配置和启用状态。
- 建立 `agent.py`、`agent_repository.py`、`agent_service.py`。
- 支持 Agent 的新增、查询、修改、删除和模型绑定。
- 暂不加入工作流和 Skill，先保证单个 Agent 定义清晰。

验收标准：能通过 Service 创建 Agent，并从 SQLite 正确读回完整设定。

### 阶段 4：Agent 管理页面

- 在页面中创建、编辑、删除和启停 Agent。
- 从已有 API 配置中选择 Agent 使用的模型。
- 编辑人设、职责和系统提示词。
- 清楚显示 API 配置不可用、Agent 停用等状态。

验收标准：在页面创建一个 Agent，刷新页面后数据仍然存在且模型绑定正确。

### 阶段 5：单 Agent 对话

- 新增独立的单 Agent 对话页面。
- 用户可以选择一个 Agent 开始多轮聊天。
- 使用 LangChain 消息类型保存用户消息、AI 消息和系统消息。
- 使用 SQLite 保存会话和历史记录，重新打开后可以继续对话。
- 支持新建会话、切换会话和清空指定会话。

验收标准：Agent 能记住同一会话前面说过的信息；不同会话之间互不污染。

### 阶段 6：工作流与多 Agent 协作

- 使用 LangGraph 构建分析、分派、执行、验证和最终回答流程。
- 分开实现 `pipeline.py` 与 `pipeline_manager.py`。
- 支持配置“哪个 Agent 可以把任务交给哪个 Agent”。
- 对话页面分为“单 Agent 对话”和“工作流处理”两个入口。
- 快速模式允许前台 Agent 直接回答，完整模式经过分析与验证节点。

验收标准：页面可配置一条简单工作流，并能看到任务经过的 Agent 与最终结果。

### 阶段 7：Tool 与 MCP

- 接入本地 Python Tool 和 MCP Server。
- 每个 Agent 可以绑定允许使用的 Tool 与 MCP 工具。
- MCP 服务放入独立目录，方便开发、测试和后续随应用打包。
- 为工具调用加入超时、错误提示和调用记录。

验收标准：Agent 可以根据问题决定是否调用工具，并正确取得 MCP 返回结果。

### 阶段 8：Skill 系统

- 定义统一的 Skill 元数据、安装状态、启用状态和来源信息。
- 每个 Agent 理论上可使用所有 Skill，但默认只启用其职业 Skill。
- 在配置中简易设置每个 Agent 允许使用和默认开启的 Skill。
- 支持全局封印 Skill，被封印后任何 Agent 都不能调用。
- 接入绘图师和 draw.io Skill，生成可编辑的 `.drawio` 文件。

验收标准：同一个 Skill 可对不同 Agent 分别启用或关闭；全局封印优先级最高。

### 阶段 9：Skill 市场

- 在平台内搜索 SkillsMP 和 ClawHub。
- 将搜索结果转换为统一的展示格式，但保留来源、作者和原始地址。
- 用户点击安装后，下载并校验 Skill，再登记到本地 Skill 仓库。
- 安装前显示将写入的文件和需要的权限，失败时不留下半安装状态。

验收标准：能从至少一个市场搜索、预览、安装、启用和卸载一个 Skill。

### 阶段 10：LlamaIndex 知识库

- 使用 LlamaIndex 完成文档读取、索引、检索和引用。
- 将知识检索能力交给“图书管理员”Agent。
- 其他 Agent 可以通过工作流向图书管理员请求资料。
- 检索结果必须包含来源，避免把 MCP Resource 与 RAG 索引混为一体。

验收标准：导入本地文档后，Agent 能回答相关问题并给出引用来源。

### 阶段 11：桌面应用与发布

- 在 Web 功能稳定后再接 Electron 桌宠前端。
- 将 Python 后端、本地 MCP 服务和所需运行资源一起打包。
- 分别验证 Windows、macOS 和 Linux 的启动、路径、权限与更新方式。
- 明确哪些组件随应用分发，避免要求最终用户另装 Python 或 Node.js。

验收标准：全新系统环境安装后可以直接启动、聊天并调用内置工具。

## 当前检查点

下一步不是直接开发 Agent 管理，而是先由用户验收阶段 2 的 API 管理页面和真实模型测速。验收完成后，再开始阶段 3。
