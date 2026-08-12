# my_agent 第一版

这是课程 L1-L9 内容的第一个整合版本，暂时只有命令行后端，没有前端。

## 目录

```text
my_agent/
├─ agent.py       # 模型配置、角色节点、LangGraph 和命令行入口
├─ tool.py        # 与 Agent 同进程的 LangChain 工具
├─ data/
│  └─ profile.json # 持久化用户身份，默认是“主人”
└─ mcp/
   └─ server.py   # 可被其他 MCP Host 复用的本地 stdio 工具
```

## 普通模式

```text
梅贝尔（陪伴者与对话主体）
  -> 分析师
  -> Python 讲师 / 时间播报员 / 图书管理员 / 绘图师 / 技能管理员 / 身份管理员 / 通用专家
  -> 验证员
  -> 梅贝尔交付最终回答
```

时间播报员调用 `mcp/server.py` 的 `get_current_time`。图书管理员目前只有接口占位；L10-L12 完成后再接入 LlamaIndex 文档加载、索引、检索和引用。

## 快速模式

```text
用户 -> 梅贝尔直接回答 -> END
```

快速模式不会经过分析师、专家或验证员，速度更快，但复杂问题的可靠性较低。

## 运行

从 `backend` 目录执行：

```powershell
python -m my_agent.agent
```

选择 `normal` 或 `fast`，再输入问题。测试问题：

```text
现在几点？
请解释 Python 装饰器。
请查询项目知识库中的打包规范。
```

第三个问题会由图书管理员明确告知知识库尚未接入，这是当前阶段的正确行为。

绘图测试：

```text
请画一个“用户提问、分析、调用工具、返回答案”的流程图。
```

绘图师通过 MCP `create_drawio_flowchart` 生成 `.drawio` 文件，输出目录是 `my_agent/output/`。文件可以使用 draw.io 桌面版或 diagrams.net 打开和编辑，不依赖 VS Code 扩展。

绘图能力的设计参考 [Agents365-ai/drawio-skill](https://github.com/Agents365-ai/drawio-skill)。该 Skill 是一套供编码 Agent 使用的绘图工作流和辅助脚本，并不是桌宠运行时可以直接导入的 Python 库。因此项目采用：

```text
drawio-skill 的工作流与规则
  -> 转化为项目内的绘图 MCP 工具
  -> 绘图师 Agent 调用
```

绘图能力放在 MCP，而不是 `tool.py`：它会生成外部文件，并适合被桌宠和其他 MCP Host 复用。`tool.py` 保留只属于当前 Agent 进程的身份和运行环境工具。

当前第一版只实现纵向简单流程图。后续绘图课程将逐步接入 drawio-skill 中的结构校验、布局、PNG/SVG/PDF 导出和 draw.io CLI 检测。打包时需要把实际使用的脚本及其许可证一起纳入项目，不能依赖开发电脑上的 `~/.codex/skills` 目录。

## Skill 市场与安装

项目使用独立的 `my_agent/skills/`，不依赖 Codex 的 `$CODEX_HOME/skills`。第一版支持已审核的 SkillsMP/ClawHub 条目映射到 GitHub 源仓库，也支持公开 GitHub Skill 仓库。

安装器会检查 HTTPS 来源、下载大小、ZIP 越界路径和 `SKILL.md`。安装后默认禁用，并且 Skill 自带脚本默认禁止自动执行。

技能管理员只接受明确命令：

```text
列出技能
确认安装 https://skillsmp.com/skills/agents365-ai-drawio-skill-skills-drawio-skill-skill-md
确认安装 https://clawhub.ai/agents365-ai/drawio-pro-skill
确认启用 drawio-skill
禁用 drawio-skill
```

普通的“这个 Skill 怎么样”不等于安装授权。安装和启用是两个动作，梅贝尔不能静默完成。当前启用只允许读取 `SKILL.md` 指令，不允许自动运行下载包里的脚本；脚本权限、依赖安装和沙箱留到插件权限课程。

## Skill 启动命令

每个 Skill 的快捷入口配置在 `backend/config.yaml`：

```yaml
skill_shortcuts:
  drawio-skill:
    trigger: /drawio
    route: diagram_artist
    default_input: 请说明你想绘制的图和步骤。
    enabled: true
  skill-manager:
    trigger: /skills
    route: skill_manager
    default_input: 列出技能
    enabled: true
```

使用示例：

```text
/drawio 画一个用户登录流程
/skills
```

快捷命令会跳过分析师的模型分类，直接进入配置的专家节点，但仍经过验证员和梅贝尔。即使当前选择了快速模式，显式 Skill 命令仍会执行对应 Skill。

当前命令行阶段的“启动按键”是 `/命令`。系统级组合键（例如 `Ctrl+Alt+D`）必须由 Electron 注册，后续可以把同一份 `skill_shortcuts` 配置映射为界面按钮和全局快捷键。

`route` 不能指向任意 Python 函数，只能使用代码中审核过的专家节点。安装新 Skill 后，仍需为它实现或授权对应执行器，不能仅靠修改 YAML 执行第三方脚本。

## 每个 Agent 的 Skill 权限

Skill 是否安装/启用，与某个 Agent 是否有权使用，是两层设置：

```text
Skill 注册表全局启用
  AND
config.yaml 授权给当前 Agent
  -> 当前 Agent 才能读取和使用该 Skill
```

权限矩阵位于 `config.yaml`：

```yaml
agent_skills:
  defaults: []       # 默认全部关闭
  agents:
    python_teacher:
      - python-teaching
    time_announcer:
      - current-time
    diagram_artist:
      - drawio-skill
    general:
      - general-answer
```

未列出的 Skill 默认拒绝。每个 Agent 理论上可以使用任意 Skill，只需把 Skill 名加入对应列表。例如允许通用 Agent 绘图：

```yaml
general:
  - general-answer
  - drawio-skill
```

关闭绘图师的绘图权限：

```yaml
diagram_artist: []
```

此时即使 `/drawio` 能路由到绘图师，节点也会返回权限拒绝，不会调用 MCP。

初始建议只开放职业 Skill：时间播报员使用时间、绘图师使用 drawio、身份管理员修改身份、技能管理员管理 Skill。不要把所有 Skill 放进 `defaults`，否则等同于默认全部授权。

## 身份与称呼

默认身份保存在 `data/profile.json`：

```json
{
  "identity": "主人"
}
```

在普通模式中可以直接告诉梅贝尔：

```text
以后称呼我为老师。
```

分析师会把请求交给身份管理员，身份管理员调用 `tool.py` 中的 `update_user_identity`，并将新身份写入 JSON。之后的新回答会读取最新身份。身份不能为空，最长 30 个字符。

身份记录写入磁盘，因此程序退出后仍然保留。它与对话历史不是同一种存储。

## 多轮对话历史

命令行现在会持续读取问题，输入 `exit` 或 `quit` 才结束。每一轮都使用相同的：

```text
thread_id = desktop-user
```

`AgentState.messages` 使用 LangGraph 的 `add_messages` 追加 HumanMessage 和 AIMessage，`InMemorySaver` 按 `thread_id` 保存历史。因此可以测试：

```text
我正在学习 Python 列表。
我刚才说在学习什么？
```

当前历史只保存在内存，程序退出后消失。身份存储在 JSON 中，所以身份不会随程序退出丢失。后续 SQLite 课程再把对话历史改成持久化存储。

## 设计边界

- 梅贝尔不是前台或客服。她是始终与主人直接交谈的陪伴者；分析师和专家只是她在幕后使用的能力，不向用户播报“转交”过程。
- 角色提示只参考公开资料中的神秘、从容、温柔而难以捉摸的气质，不复制游戏台词，也不影响事实准确性。
- `InMemorySaver` 只在当前进程保存对话 State，退出后消失；用户身份单独持久化到 JSON。
- 当前一次只路由给一个专家；多专家并行和失败重试后续再加入。
- LlamaIndex 不提前伪造，等 L10-L12 按课程接入。
- 前端、FastAPI、WebSocket 和打包仍按后续课程完成。
- 绘图实现以 `Agents365-ai/drawio-skill` 为参考，不依赖 `vscode-drawio`。

## 管理控制台

启动本地控制台：

```powershell
python -m my_agent.console_api
```

默认地址：

```text
http://127.0.0.1:8765
```

模块职责：

```text
console_ui/          只负责界面、表单状态和调用 JSON API
console_api.py       本地 HTTP API 与静态文件服务
agent.py             实际 LangGraph Agent 运行逻辑
agent_manager.py     Agent 定义、人格和 Skill 绑定管理
pipline.py           工作流领域模型（按项目要求保留该文件拼写）
pipline_manager.py   工作流保存、校验和删除
skill_manager.py     市场映射、安装、启用与全局封印
```

控制台支持：

- 添加、编辑、启停和删除 Agent 定义。
- 编辑 Agent 人格、职责和 Skill 多选绑定。
- 创建工作流并配置 `source -> target -> condition` 交接边。
- 搜索项目审核过的 SkillsMP/ClawHub 目录，并跳转市场继续搜索。
- 下载 Skill、启用/禁用 Skill，以及全局封印。

全局封印优先级最高：封印后会同时关闭 Skill，全体 Agent 都不能加载该 Skill。Agent Skill 绑定会同步到 `config.yaml`。

第一版新增 Agent 是“管理定义”，不会自动生成并执行任意 Python 节点。现有职业节点仍由 `agent.py` 明确实现和审核。要让新 Agent 参与真实运行，需要后续为它绑定受控执行器；不能仅凭 UI 中的一段提示词获得文件、网络或进程权限。
