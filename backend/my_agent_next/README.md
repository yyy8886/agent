# my_agent_next

这是 AI 桌面助手的新版本后端。项目采用“先做一个能运行的小功能，验收后再增加下一层”的方式开发。

当前已经具备：

- OpenAI、DeepSeek、Ollama 和 OpenAI 兼容代理的 API 配置管理
- API 管理页面与真实模型测速
- Agent 创建、编辑、删除、人设配置、模型绑定与 Skill 绑定
- 单 Agent 多轮聊天、会话管理和 SQLite 历史记录
- 长对话压缩摘要和用户长期记忆
- LangChain Tool Calling 与模型—工具循环
- 文件、搜索、网页、命令执行和向用户提问等 Tool
- 手动确认与自动执行两种工具权限模式
- `SKILL.md` 加载及 `scripts/`、`references/` 资源提示
- SkillsMP、ClawHub 和 GitHub Skill 搜索、查看、安装与卸载接口
- draw.io Skill 及其脚本资源

当前尚未完成：

- LangGraph 多 Agent 工作流
- 完整的 Skill 渐进加载、系统/用户目录分离和安全脚本执行器
- LlamaIndex 知识库
- Electron 桌宠前端
- 跨平台打包和发布

## 技术栈

| 技术 | 用途 |
| --- | --- |
| Python 3.11/3.12 | 后端语言 |
| FastAPI + Uvicorn | HTTP 接口、页面服务和 SSE 聊天接口 |
| HTML + CSS + JavaScript | 当前 Web 管理台和聊天页面 |
| LangChain | 消息、模型统一接口、Tool Calling |
| OpenAI / DeepSeek / Ollama | 可切换的模型提供方 |
| SQLite | API、Agent、会话、消息和用户记忆持久化 |
| YAML | 服务和聊天参数配置 |
| python-dotenv | 从 `.env` 读取真实 API Key |
| httpx | 网页读取和 Skill 市场请求 |
| draw.io Desktop CLI | `.drawio` 生成、检查和导出 |

项目依赖中还保留了 MCP 与 LangGraph 相关库，但当前 `my_agent_next` 的主要聊天流程是用 Python 循环编排，尚未迁移为 LangGraph。

## 分层结构

```text
浏览器页面
    ↓ HTTP / SSE
FastAPI 接口层
    ↓
Service 业务层
    ↓
Repository 数据层
    ↓
SQLite
```

- 接口层接收请求和返回响应。
- Service 决定业务应该怎样执行。
- Repository 只负责从 SQLite 读取和保存数据。
- 页面只处理显示和用户操作，不直接访问数据库。

## 当前目录

```text
my_agent_next/
├─ app/
│  ├─ api_profile*.py          # 模型 API 配置领域、业务与存储
│  ├─ agent_profile*.py        # Agent 配置领域、业务与存储
│  ├─ chat_api.py              # 会话和 SSE 聊天接口
│  ├─ chat_service.py          # 消息组装、模型调用和工具循环
│  ├─ chat_repository.py       # 会话与消息存储
│  ├─ user_memory*.py          # 用户长期记忆
│  ├─ marketplace_api.py       # Skill 市场搜索、安装与卸载
│  ├─ tools/                   # 模型可调用的 Tool
│  ├─ static/index.html        # 当前 Web 控制台
│  └─ web_server.py            # FastAPI 应用入口
├─ skills/
│  ├─ _loader.py               # 解析本地 SKILL.md
│  ├─ user-memory/             # 项目自有记忆 Skill
│  └─ ...                      # 内置或用户安装的其他 Skill
├─ data/app.db                 # SQLite 数据库
├─ scripts/                    # 项目维护脚本
├─ tests/                      # 自动测试
└─ config.yaml                 # 服务和聊天参数
```

## 一次聊天如何运行

```text
用户发送消息
→ FastAPI 接收
→ 找到 Agent 和绑定模型
→ 组装人设、Skill、长期记忆、摘要和最近历史
→ LangChain 调用模型
→ 模型需要信息时提出 Tool Call
→ 权限层确认是否允许
→ 执行 Tool，把 ToolMessage 交还模型
→ 模型继续思考，直到输出最终回答
→ SSE 将结果发送给页面
→ SQLite 保存消息并按需要压缩历史、提取记忆
```

当前所谓“流式输出”是模型完整返回后再分块发送，并非模型原生 token streaming。

## Tool 与 Skill

```text
模型 = 负责思考的大脑
Skill = 告诉模型怎样完成专业任务的说明书
Tool = 真正读取文件、访问网页或运行程序的手
```

当前 Tool 包括文件读写、编辑、搜索、网页访问、`run_bash` 和向用户提问。所有模型目前绑定同一组 Tool；这是开发阶段实现，后续需要改成按 Agent 和 Skill 授予最小权限。

当前 Skill 会把完整 `SKILL.md` 注入模型，并列出附带的脚本和参考资料。下一步需要解决 Codex Skill 中 `<this-skill-dir>`、`python3`、Codex 专用 Tool 等兼容问题，并增加安全的 `run_skill_script`。

## 配置与密钥

`config.yaml` 保存普通运行参数，例如服务端口、上下文长度和 Agent 循环次数。

SQLite 只保存 API Key 的环境变量名称：

```text
api_key_env = OPENAI_API_KEY
```

真正的 Key 放在 `backend/.env` 或未来的操作系统安全存储中：

```text
OPENAI_API_KEY=真实密钥
```

`.env` 必须加入 `.gitignore`，发布程序时也不能把开发者自己的 Key 打包进去。

## 启动

在 `backend` 目录激活虚拟环境后运行项目现有启动脚本：

```powershell
python run_server.py
```

实际端口以启动脚本或 `config.yaml` 使用的入口为准。不要同时启动多个入口，否则可能出现同一个端口被多个 Python 进程占用。

## 当前风险与下一步

1. 先修正 Skill 路径和运行时兼容，使 `drawio-skill` 能稳定找到自身脚本。
2. 增加只允许运行 Skill 自带脚本的 `run_skill_script`，减少通用 `run_bash` 风险。
3. 建立 `skills/.system/` 和用户安装 Skill 的来源规则。
4. 按 Agent 与 Skill 分配 Tool，不再默认绑定全部 Tool。
5. 为市场安装增加临时目录、路径检查、权限展示和失败回滚。
6. 再用 LangGraph 实现多 Agent 分析、分派、执行、验证和人工确认。

## 开发纪律

- 每次只完成一个可验收步骤。
- 修改原文件前先产生副本或可恢复版本。
- Tool 调用默认由用户确认，尤其是 Bash、网络、安装与删除操作。
- 市场 Skill 和网页内容属于不可信输入，不能自动获得完整系统权限。
- 每个阶段同时补充说明、测试和真实运行验收。
