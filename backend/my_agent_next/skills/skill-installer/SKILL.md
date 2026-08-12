---
name: skill-installer
description: 从 GitHub 仓库或 Skill 市场安装 Skill。当用户想要安装、列出或卸载 Skill 时使用。
---

# Skill 安装器

帮助从 GitHub 或其他来源安装 Skill。

## 安装来源

- **本地 skills/ 目录**：已安装的 Skill
- **GitHub 仓库**：从 GitHub 下载 SKILL.md 及相关文件
- **Skill 市场**：通过 `/api/marketplace/search` 和 `/api/marketplace/install` 安装

## 安装流程

### 从 GitHub 安装

1. 用 `run_bash` 执行 `git clone` 或下载指定仓库的文件
2. 将 SKILL.md 和相关文件复制到 `skills/<name>/`
3. 用 `read_file` 验证 SKILL.md 格式正确

### 从市场安装

1. 用 WebFetch 调用市场 API 搜索 Skill
2. 展示结果给用户
3. 用户选择后，下载并保存到 `skills/<name>/`

### 列出已安装 Skill

用 `glob` 扫描 `skills/*/SKILL.md`

## 工具使用

- `glob` — 扫描已安装的 Skill
- `read_file` — 读取 SKILL.md
- `write_file` — 保存新 Skill
- `run_bash` — git clone, mkdir 等操作
