# 重建与 Linux 启动指南

本文说明代码修改后如何重新生成 Windows 桌面安装包，以及如何在 Linux/WSL 和 Docker 中启动 My Agent Next。

## 一、Windows 桌面版重新打包

修改后端或前端代码后，在 PowerShell 执行：

```powershell
cd C:\Users\yanzichen\Desktop\agent\desktop
.\build-windows.bat
```

脚本会自动：

1. 安装或确认 npm 依赖。
2. 使用 `backend\.venv` 重新构建 PyInstaller 后端。
3. 使用 Electron Builder 生成 NSIS 安装包。

成功输出：

```text
desktop\dist\My Agent Next Setup 0.1.0.exe
```

如果只想重新生成安装器，且后端没有变化：

```powershell
cd C:\Users\yanzichen\Desktop\agent\desktop
npm exec electron-builder -- --win nsis
```

如果提示 Electron 下载超时，可以先设置镜像：

```powershell
$env:ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
npm exec electron-builder -- --win nsis
```

如果 PyInstaller 提示文件被占用，先关闭桌面版和旧后端进程，再重新执行 bat。不要删除用户数据目录。

## 二、Docker 模式重建与启动

代码修改后，必须重新构建镜像。进入 WSL/Linux 终端：

```bash
cd /mnt/c/Users/yanzichen/Desktop/agent/backend
docker compose down
docker compose build --no-cache backend
docker compose up -d
```

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs --tail 100 backend
```

正常状态应显示 `Up (healthy)`。接口检查：

```bash
curl http://127.0.0.1:19845/api/health
```

不要使用 `docker compose down -v`，否则可能清理 Docker 卷。当前项目的数据、Skill 和 `.env` 通过目录挂载保存，不会因为普通 `down` 丢失。

## 三、Linux 原生模式

### 1. 创建虚拟环境

Ubuntu/Debian 首次使用需要安装 venv 支持：

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
```

在项目目录创建 Linux 虚拟环境：

```bash
cd /mnt/c/Users/yanzichen/Desktop/agent/backend
python3 -m venv .venv-linux
source .venv-linux/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

### 2. 启动后端

```bash
source .venv-linux/bin/activate
python -m uvicorn my_agent_next.app.web_server:app \
  --host 127.0.0.1 \
  --port 19845
```

浏览器访问：

```text
http://127.0.0.1:19845
```

如果要让局域网其他设备访问，将 host 改为 `0.0.0.0`，并配置防火墙。

### 3. 启动 Linux Electron 桌面壳

Linux 桌面需要图形环境和 Node.js：

```bash
cd /mnt/c/Users/yanzichen/Desktop/agent/desktop
npm install
npm start
```

在无图形界面的服务器上不要启动 Electron，使用上面的 Uvicorn 命令并通过浏览器访问。

## 四、MCP 路径规则

MCP 工作目录支持绝对路径和相对路径：

```text
绝对路径：直接使用，例如 D:\\Tools\\weather-mcp 或 /opt/weather-mcp
Windows/Linux 桌面安装版相对路径：相对于用户数据目录
Docker 相对路径：相对于 /app
开发模式相对路径：相对于项目 backend
```

推荐配置为相对路径：

```text
工作目录：mcp/weather
参数 JSON：["server.py"]
```

外部安装的 MCP 软件可以填写绝对路径，但该配置只能在对应机器上直接使用。

## 五、发布前检查

```text
Windows：desktop\\dist\\My Agent Next Setup 0.1.0.exe 存在
Docker：docker compose ps 显示 healthy
Linux：/api/health 返回 {"status":"ok"}
MCP：相对路径和绝对路径各测试一次
数据：确认 data/app.db、skills 和 .env 未被覆盖
```

