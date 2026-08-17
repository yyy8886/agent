# Miao Agent Next Linux 迁移指南

本文用于把 Miao Agent Next 从 Windows 迁移到 Ubuntu/Linux。推荐使用 Git 或压缩包迁移项目源码，再在 Linux 上重新创建虚拟环境。

## 1. 迁移原则

- 只迁移源码、配置和持久化数据，不迁移 Windows 的 `.venv`。
- Linux 上重新创建 `.venv-linux`，避免平台相关的二进制包冲突。
- 密钥放在 Linux 主机自己的 `.env` 中，不要提交到 Git。
- 数据库、附件和用户 Skill 属于持久化内容，迁移前先备份。

## 2. 获取项目

### Git 方式

```bash
git clone <你的仓库地址> my-agent-next
cd my-agent-next/backend
```

### 压缩包方式

把项目压缩包上传到 Linux 后解压：

```bash
unzip my-agent-next.zip
cd my-agent-next/backend
```

如果项目位于 Windows 挂载目录，WSL 中的路径通常类似：

```text
/mnt/c/Users/yanzichen/Desktop/agent/backend
```

生产环境更建议放在 Linux 自己的磁盘目录，而不是 `/mnt/c`，以获得更好的文件 I/O 性能。

## 3. 安装系统依赖

Ubuntu 示例：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

确认版本：

```bash
python3 --version
git --version
```

项目当前已在 Python 3.12.3 环境完成验证。Python 版本应与项目要求兼容。

## 4. 创建 Linux 虚拟环境

在 `backend` 目录执行：

```bash
python3 -m venv .venv-linux
source .venv-linux/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

每次重新打开终端后，需要重新激活：

```bash
source .venv-linux/bin/activate
```

不要复制 Windows 的 `.venv` 或 `.venv-linux` 到另一台机器；虚拟环境包含平台相关路径和二进制文件。

## 5. 迁移配置和持久化数据

从 Windows 项目复制以下内容到 Linux 项目对应位置：

```text
my_agent_next/data/app.db       # Agent、对话、工作流等数据库
my_agent_next/data/attachments/ # 对话图片附件
my_agent_next/skills/           # 用户和项目 Skill
my_agent_next/.env              # API 密钥和本地配置，手动迁移更安全
config.yaml                     # 如果项目使用了该配置文件
```

迁移前建议备份：

```bash
cp my_agent_next/data/app.db my_agent_next/data/app.db.bak
tar -czf attachments-backup.tar.gz my_agent_next/data/attachments
```

`.env` 示例（根据实际模型配置填写）：

```dotenv
OPENAI_API_KEY=your-key
DEEPSEEK_API_KEY=your-key
```

确保文件权限合适：

```bash
chmod 600 my_agent_next/.env
```

不要迁移或提交包含真实密钥的日志、截图和调试文件。

## 6. 检查 Linux 兼容性

确认代码使用相对路径或 `pathlib`，不要依赖 `C:\\Users\\...`、PowerShell 或 Windows 专用命令。Draw.io 等桌面 CLI 在纯 Linux 环境中不可用时，应跳过对应的 Windows 导出步骤，或安装 Linux 版本工具。

检查 Python 和当前目录：

```bash
which python
pwd
```

## 7. 运行 Linux 冒烟测试

在 `backend` 目录、虚拟环境已激活的情况下执行：

```bash
bash scripts/linux_smoke_test.sh
```

成功时应看到类似输出：

```text
{ "status": "ok" }
Linux FastAPI smoke test passed
```

脚本会临时启动 Uvicorn，请求 `/api/health`，然后自动停止服务。

## 8. 正式启动后端

```bash
python -m my_agent_next.app.web_server
```

默认访问地址：

```text
http://127.0.0.1:19845
```

需要局域网访问时，可使用：

```bash
uvicorn my_agent_next.app.web_server:app --host 0.0.0.0 --port 19845
```

生产环境请在反向代理、防火墙和认证策略配置完成后再暴露到公网。

## 9. 后台运行

临时运行可以使用：

```bash
nohup python -m my_agent_next.app.web_server > /tmp/my-agent-next.log 2>&1 &
```

查看日志：

```bash
tail -f /tmp/my-agent-next.log
```

长期运行建议配置 systemd，让服务自动重启并在开机时启动。服务的 `WorkingDirectory` 应指向 `backend`，`ExecStart` 应使用 `.venv-linux/bin/python`。

## 10. Electron 工作台（可选）

Electron 会优先寻找当前平台可用的虚拟环境，并启动 FastAPI 后再打开内置 Chromium 工作台。Linux 上先安装桌面依赖和 Node.js/npm，再在 `desktop` 目录执行：

```bash
npm install
npm start
```

如果 npm 提示 Electron 或 electron-winstaller 的安装脚本尚未批准，先执行：

```bash
npm approve-scripts electron electron-winstaller
npm install
npm start
```

如果出现 Electron 没有执行权限：

```bash
chmod +x node_modules/electron/dist/electron
npm start
```

服务器环境没有图形界面时，只运行 FastAPI/Python Worker，不启动 Electron。

## 11. WSL 特别说明

WSL 是 Windows 上的 Linux 运行层，不是 Linux 部署的必要组成部分。WSL 中看到 `/mnt/c/...` 是因为项目位于 Windows 磁盘；部署到真正 Linux 服务器时，使用 Linux 本地路径即可。若 WSL 提示 localhost 代理未镜像，不影响同一 WSL 会话内的服务启动和健康检查。

## 12. 常见问题

### `ensurepip is not available`

安装虚拟环境组件后重试：

```bash
sudo apt install -y python3.12-venv
rm -rf .venv-linux
python3 -m venv .venv-linux
```

### `uv: command not found`

当前项目可以直接使用 `pip install -e .`，不依赖 `uv`。只有在需要同步 `uv.lock` 时才额外安装 uv。

### 端口被占用

换一个端口启动：

```bash
uvicorn my_agent_next.app.web_server:app --host 127.0.0.1 --port 19846
```

### API 返回 402 Insufficient Balance

检查 Linux `.env` 中对应模型供应商的密钥、账户余额和 Base URL。该错误不是 Linux 迁移本身造成的。

## 13. 迁移完成清单

- [ ] Linux 已安装 Python、venv、pip 和 Git
- [ ] 已创建并激活 `.venv-linux`
- [ ] 已执行 `pip install -e .`
- [ ] 已迁移 `app.db`、附件、Skill 和配置
- [ ] 已重新填写并保护 `.env`
- [ ] `bash scripts/linux_smoke_test.sh` 通过
- [ ] 正式服务可以访问 `/api/health`
- [ ] 已确认端口、防火墙和日志策略
