# Windows 桌面版打包说明

本项目的 Windows 桌面版由 Electron 提供界面，由 PyInstaller 将 FastAPI/Python Worker 打包为内置的 `my-agent-next-backend.exe`。用户安装后不需要单独安装 Python、创建虚拟环境或运行 Docker。

## 一、开发环境

需要安装：

- Windows 10/11（建议 x64）
- Node.js 18 或更高版本
- npm
- Python 3.12（仅用于开发者打包后端）

首次准备后端环境：

```powershell
cd C:\Users\yanzichen\Desktop\agent\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install pyinstaller
```

## 二、构建后端可执行文件

在 `backend` 目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows_backend.ps1
```

成功后应生成：

```text
backend\dist\my-agent-next-backend\my-agent-next-backend.exe
```

该目录包含运行所需的 Python 依赖、页面资源和内置 Skill。不要把 `.venv` 或源码复制给最终用户。

## 三、构建 Electron 安装包

也可以直接双击 `build-windows.bat` 一键完成依赖安装、后端构建和 Windows 安装包构建。命令行方式如下：

```powershell
cd C:\Users\yanzichen\Desktop\agent\desktop
npm install
npm test
npm run dist:win
```

`dist:win` 会先自动构建 PyInstaller 后端，再由 electron-builder 生成 NSIS 安装包。输出位置是：

```text
desktop\dist\My Agent Next Setup 0.1.0.exe
```

若只需要生成未安装目录用于快速检查，可执行：

```powershell
npm run pack
```

## 四、用户运行与数据位置

安装后双击桌面快捷方式即可启动。Electron 会自动启动内置后端，并等待健康检查通过后打开工作台。

用户数据不会写入安装目录，而是写入：

```text
%APPDATA%\My Agent Next\backend
```

其中包括数据库、用户 Skill、附件、工作流和配置。后端日志位于：

```text
%APPDATA%\My Agent Next\backend\data\backend.log
```

升级安装包时该目录会保留，因此不会覆盖用户的 Agent、对话、API 配置或 Skill。卸载程序默认不主动删除这些数据，如需清理可手动删除上述目录。

## 五、常见问题

### 安装包构建长时间无输出

首次运行 electron-builder 可能下载 NSIS/Wine 等构建工具。检查网络后重新执行 `npm run dist:win`；也可以先执行 `npm test` 和 `npm run pack` 验证应用文件本身。

### 启动时提示后端超时

查看 `%APPDATA%\My Agent Next\backend\data\backend.log`。确认杀毒软件没有拦截内置 exe，并检查端口是否被占用。

### 没有模型回答

在应用的 API 配置页面填写 API Key。密钥保存在用户数据目录的 `.env`，不要把它提交到 Git 或打包进安装包。

### Ollama 无法连接

桌面版只负责调用 Ollama 服务；需要在本机另行启动 Ollama，并在 API 配置中填写正确的 Base URL（通常为 `http://127.0.0.1:11434/v1`）。

## 六、发布前检查

1. `npm test` 全部通过。
2. `npm run dist:win` 成功生成 NSIS 安装包。
3. 在干净 Windows 用户目录安装并启动，能打开工作台。
4. 创建 Agent、发送消息、上传图片、运行 Skill 和工作流。
5. 重启应用后数据、Skill 和对话仍然存在。
6. 确认安装包和日志中没有 API Key 等敏感信息。
