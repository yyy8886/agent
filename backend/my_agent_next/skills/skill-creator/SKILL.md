---
name: skill-creator
description: 创建新 Skill 或更新已有 Skill。当用户想要创建或修改 Skill 时使用此 Skill。
---

# Skill 创建器

此 Skill 帮助创建符合本系统规范的新 Skill。

## Skill 格式

每个 Skill 是一个目录，包含一个 `SKILL.md` 文件：

```
skills/<skill-name>/
├── SKILL.md              # 必需：YAML frontmatter + markdown 指令
├── references/            # 可选：详细文档（LLM 按需读取）
└── scripts/               # 可选：辅助脚本（LLM 通过 run_bash 调用）
```

### SKILL.md 结构

```markdown
---
name: skill-name
description: 一句话描述 + 触发条件。这是 LLM 决定何时使用此 Skill 的主要依据。
---

# 标题

## 概述
简要说明

## 触发条件
- 何时应使用此 Skill

## 执行流程
1. 步骤一
2. 步骤二

## 输出格式
期望的输出结构
```

## 创建流程

1. **理解需求**：问清楚 Skill 要解决什么问题
2. **规划内容**：确定需要哪些 references/ 和 scripts/
3. **创建目录**：用 `run_bash` 创建 `skills/<name>/` 目录
4. **编写 SKILL.md**：用 `write_file` 写入 SKILL.md
5. **验证**：用 `read_file` 读回检查格式

## 设计原则

- **简练**：LLM 已经很聪明，只加 LLM 不知道的知识
- **description 是关键**：这是 Skill 的触发条件，要写清楚何时使用
- **SKILL.md 控制在 500 行以内**：详细内容放 references/
- **不要创建无关文件**：不需要 README、CHANGELOG 等

## 工具使用

创建 Skill 时你可以使用以下工具：
- `write_file` — 写入 SKILL.md
- `read_file` — 读取检查
- `glob` — 查找已有 Skill
- `run_bash` — 创建目录等 shell 操作
