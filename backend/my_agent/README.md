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
  -> Python 讲师 / 时间播报员 / 图书管理员 / 绘图师 / 身份管理员 / 通用专家
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
