# L1 模型调用与跨平台基础

这一课只完成三件事：

1. `L1.1`：规范 Python 项目配置，并在命令行调用 DeepSeek。
2. `L1.2`：理解如何切换 DeepSeek、OpenAI GPT 和本地 Ollama。
3. `L1.3`：理解同一项目如何在 Windows、macOS、Linux 上开发和发布。

请严格按顺序学习。先完成当前检查点，把输出或完整报错发给我，通过后再继续。不要一次复制完所有命令。

## 完成本课后的目录

这只是本课结束时的目标，不要现在一次创建所有文件：

```text
backend/
├─ .env                           # 本地密钥，不提交
├─ .gitignore
├─ .venv/                         # 当前系统的虚拟环境，不提交
├─ config.yaml                    # 非敏感运行参数，应提交
├─ pyproject.toml                 # Python 项目和依赖声明，应提交
└─ lecture/
   └─ L1/
      ├─ README.md                # 本文件
      └─ lesson_01_chat.py        # 多模型单轮问答（一个文件搞定）
```

注：`lesson_01_chat.py` 放在 `lecture/L1/` 子目录下，它会自动向上查找项目根目录的 `config.yaml` 和 `.env`。不再需要单独的 `lesson_01_providers.py`。

## L1.1 DeepSeek 首次调用与项目配置

### 学习目标

完成 L1.1 后，你应该能够：

- 区分 Python 解释器、虚拟环境、`pip` 和项目依赖。
- 解释 `pyproject.toml`、`config.yaml`、`.env` 的不同职责。
- 解释 provider、`base_url`、API Key 和 model ID。
- 输入"你好"并看到 DeepSeek 回复。
- 根据错误判断问题发生在文件、环境、配置还是 API 层。

### 原理先行：一次调用经过什么

```text
键盘输入"你好"
  -> lesson_01_chat.py
  -> 从 config.yaml 读取 app.active_model → 定位到具体模型配置
  -> 读取 model、temperature、base_url 等普通参数
  -> 从 .env 读取 API Key（根据 provider 自动选对应的环境变量）
  -> 根据 provider 选择对应客户端（ChatDeepSeek / ChatOpenAI / ChatOllama）
  -> 组装 HTTP 请求 → 发送到 API 服务器
  -> 返回 AIMessage
  -> response.content
  -> 命令行输出
```

此时还不是 Agent。程序不会自主选择工具、循环决策或持久记忆，只完成一次模型调用。

### 检查点 1：确认工作目录与现有文件

你当前应位于：

```text
C:\Users\yanzichen\Desktop\agent\backend
```

执行：

```powershell
Get-Location
Get-ChildItem -Force
```

`Get-Location` 用于确认相对路径从哪里开始，`-Force` 会显示 `.env`、`.venv` 等隐藏项。

当前目录中的 `pyproject.toml` 文件名前带有不可见的 `U+200B` 字符。先修正：

```powershell
Get-ChildItem *pyproject.toml | Rename-Item -NewName pyproject.toml
Get-ChildItem pyproject.toml
```

第二条命令应准确显示 `pyproject.toml`。如果提示目标文件已经存在，先停止并把 `Get-ChildItem -Force` 的输出发给我，不要删除任何文件。

### 检查点 2：确认 Python 与虚拟环境

执行：

```powershell
python --version
python -m pip --version
python -c "import sys; print(sys.executable)"
```

推荐 Python 3.11 或 3.12。你当前使用 Python 3.12，适合本课程。

最后一条命令的预期路径是：

```text
C:\Users\yanzichen\Desktop\agent\backend\.venv\Scripts\python.exe
```

如果显示系统 Python 路径，激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell 禁止运行脚本，只对当前窗口临时放行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

为什么使用 `python -m pip`，而不是直接使用 `pip`？因为前者明确要求"由当前这个 Python 执行 pip"，可以减少把包装进另一个 Python 环境的情况。

### 检查点 3：编写 `pyproject.toml`

打开 `backend/pyproject.toml`，确认内容为：

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "desktop-ai-backend"
version = "0.1.0"
description = "Python backend for the desktop AI assistant learning project"
requires-python = ">=3.11,<3.14"
dependencies = [
    "langchain-deepseek",
    "langchain-ollama",
    "langchain-openai",
    "python-dotenv",
    "pyyaml",
]
```

逐项理解：

| 配置                | 含义                                  |
| ------------------- | ------------------------------------- |
| `build-system`    | 告诉 pip 用 setuptools 构建和安装项目 |
| `name`            | 安装后的项目名称，不是 Python 文件名  |
| `version`         | 当前项目版本                          |
| `requires-python` | 允许 Python 3.11–3.13，暂不采用 3.14 |
| `dependencies`    | 运行项目必须安装的第三方包            |

五个依赖的职责：

- `langchain-deepseek`：LangChain 官方 DeepSeek 集成（提供 `ChatDeepSeek`）。
- `langchain-ollama`：LangChain 官方 Ollama 集成（提供 `ChatOllama`）。
- `langchain-openai`：OpenAI 及兼容接口，含中转站（提供 `ChatOpenAI`）。
- `python-dotenv`：开发阶段从 `.env` 读取秘密。
- `pyyaml`：使用 `yaml.safe_load` 读取 `config.yaml`。

安装项目：

```powershell
python -m pip install --upgrade pip
python -m pip install -e .
```

`-e` 是 editable install。修改自己的 Python 代码后通常不需要重新安装；修改依赖列表后需要再次执行。

验证依赖：

```powershell
python -c "import dotenv, yaml; from langchain_deepseek import ChatDeepSeek; from langchain_ollama import ChatOllama; from langchain_openai import ChatOpenAI; print('依赖正常')"
```

预期输出：

```text
依赖正常
```

### 检查点 4：创建 `config.yaml`

在 `backend` 中创建 `config.yaml`：

```yaml
app:
  active_model: deepseek_chat       # 当前使用的模型，切换改这里即可

models:
  deepseek_chat:                    # DeepSeek V3（通用对话）
    provider: deepseek
    model: deepseek-chat
    temperature: 0.2
    timeout_seconds: 60
    max_retries: 2

  openai_gpt:                       # OpenAI 直连（可选，后续 L1.2 用）
    provider: openai
    model: gpt-5.6-sol
    temperature: 0.2
    timeout_seconds: 60
    max_retries: 2

  ollama_local:                     # 本地 Ollama（可选，后续 L1.2 用）
    provider: ollama
    model: qwen3:8b
    base_url: http://127.0.0.1:11434
    temperature: 0.2
```

注意：

- YAML 使用空格缩进，不能使用 Tab。
- 同一层级必须对齐。
- `active_model` 指向下面 `models` 中某个配置名，这就是切换模型的唯一位置。
- `provider`：决定程序创建 `ChatDeepSeek`、`ChatOpenAI` 还是 `ChatOllama`。
- `model`：提供商真实接受的 API model ID，不能随便编写。
- `temperature` 越低，输出通常越稳定；它不是"回答质量"旋钮。
- `timeout_seconds` 限制单次请求等待时间。
- `max_retries` 是客户端失败后的重试次数。
- `base_url`：API 服务器地址。不写时程序自动用 provider 默认地址；写了就覆盖（用于中转站或自建服务）。
- API Key 不得写入该文件。

先单独验证 YAML，不调用模型：

```powershell
python -c "from pathlib import Path; import yaml; print(yaml.safe_load(Path('config.yaml').read_text(encoding='utf-8')))"
```

预期看到一个 Python 字典，其中包含 `app` 和 `models`。

### 检查点 5：配置 `.env` 与 `.gitignore`

`.env` 只写秘密：

```env
DEEPSEEK_API_KEY=替换成你自己的密钥
```

（后续 L1.2 如需 OpenAI 或中转站，再加 `OPENAI_API_KEY=...`）

不要在聊天、截图、Git 提交或错误日志中展示真实值。

`.gitignore` 至少包含：

```gitignore
.env
.venv/
__pycache__/
*.egg-info/
```

三种文件的边界：

| 文件               | 保存什么                               | 是否提交 |
| ------------------ | -------------------------------------- | -------- |
| `pyproject.toml` | 项目信息和依赖                         | 是       |
| `config.yaml`    | 模型名、provider、地址、温度等普通参数 | 是       |
| `.env`           | API Key 等秘密                         | 否       |

验证变量是否存在，但不要打印密钥：

```powershell
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(bool(os.getenv('DEEPSEEK_API_KEY')))"
```

预期输出 `True`。如果是 `False`，检查文件是否真的叫 `.env`，以及变量名是否完全一致。

### 检查点 6：亲手编写首次调用

在 `backend/lecture/L1/` 下创建 `lesson_01_chat.py`，内容如下。

**关键：脚本在 `lecture/L1/` 子目录下，但它需要访问项目根目录 `backend/` 的 `config.yaml` 和 `.env`。** 因此代码开头用 `Path(__file__).resolve().parent.parent.parent` 向上三级定位到 `backend/`，后续所有路径拼接都基于这个目录。

```python
# =============================================================================
# 1. 导入依赖
# =============================================================================
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek      # DeepSeek 官方集成
from langchain_ollama import ChatOllama          # 本地 Ollama
from langchain_openai import ChatOpenAI          # OpenAI 及兼容接口（含中转站）


# =============================================================================
# 2. 定位项目根目录，加载 .env 和 config.yaml
# =============================================================================
# __file__ = lecture/L1/lesson_01_chat.py → 上三级 = backend/
backend_dir = Path(__file__).resolve().parent.parent.parent

# 加载 backend/.env，将 API Key 等敏感信息注入环境变量
load_dotenv(backend_dir / ".env")

# 解析 backend/config.yaml
config_path = backend_dir / "config.yaml"
with config_path.open("r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

# config.yaml 结构：app.active_model 指定当前用哪个模型
#                 models.<key> 下是每个模型的具体参数
active_model = config["app"]["active_model"]
model_config = config["models"][active_model]


# =============================================================================
# 3. 根据 provider 获取 API Key 和 base_url
# =============================================================================
provider = model_config["provider"]  # deepseek | openai | ollama

# provider → 环境变量名（Ollama 本地运行无需 Key）
PROVIDER_ENV_MAP = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai":   "OPENAI_API_KEY",
    "ollama":   None,
}
# provider → 默认 API 地址（config.yaml 中配了 base_url 会覆盖）
PROVIDER_DEFAULT_BASE_URL = {
    "deepseek": "https://api.deepseek.com",
    "openai":   "https://api.openai.com/v1",
    "ollama":   "http://127.0.0.1:11434",
}

env_var = PROVIDER_ENV_MAP.get(provider)
if env_var:
    api_key = os.getenv(env_var)
    if not api_key:
        raise RuntimeError(f"未找到 {env_var}，请检查 backend/.env")
else:
    api_key = "not-needed"  # Ollama 无需 Key

# config.yaml 有 base_url 就用它（如中转站），否则用 provider 默认值
base_url = model_config.get("base_url") or PROVIDER_DEFAULT_BASE_URL.get(provider, "")


# =============================================================================
# 4. 创建模型实例 — provider 不同，用的类也不同
# =============================================================================
# 三种 provider 通用的参数
common_kwargs = {
    "model": model_config["model"],
    "temperature": model_config["temperature"],
}

if provider == "deepseek":
    model = ChatDeepSeek(
        **common_kwargs,
        api_key=api_key,
        base_url=base_url,
        timeout=model_config.get("timeout_seconds", 60),
        max_retries=model_config.get("max_retries", 2),
    )
elif provider == "openai":
    # ChatOpenAI 可连接 OpenAI 官方，也可连接任何兼容的中转站（改 base_url 即可）
    model = ChatOpenAI(
        **common_kwargs,
        api_key=api_key,
        base_url=base_url,
        timeout=model_config.get("timeout_seconds", 60),
        max_retries=model_config.get("max_retries", 2),
    )
elif provider == "ollama":
    model = ChatOllama(
        **common_kwargs,
        base_url=base_url,
    )
else:
    raise RuntimeError(f"不支持的 provider: {provider}")


# =============================================================================
# 5. 交互：读取用户输入 → 调用模型 → 打印回复
# =============================================================================
question = input("你：").strip()
if not question:
    raise SystemExit("输入不能为空")

response = model.invoke(question)       # 向 API 发送请求
print(f"{provider}：{response.content}")  # 打印回复文本
```

关键代码解释：

- `Path(__file__).resolve().parent.parent.parent`：从脚本所在目录向上三级找到项目根目录。无论从哪个目录启动脚本都正确。
- `load_dotenv(backend_dir / ".env")`：显式传入绝对路径，不依赖当前工作目录。
- `yaml.safe_load(...)`：安全解析 YAML，不使用能构造任意 Python 对象的不安全方式。
- `PROVIDER_ENV_MAP` 和 `PROVIDER_DEFAULT_BASE_URL`：两张字典表完成 provider → Key/地址的映射。新增 provider 只需加一行。
- `model_config.get("base_url") or PROVIDER_DEFAULT_BASE_URL.get(...)`：config.yaml 有 `base_url` 就用它（中转站场景），没写就用 provider 默认值。
- `if/elif` 根据 `provider` 创建不同的客户端类。
- `model.invoke(...)`：真正发起一次同步 HTTP 请求。
- `response.content`：取出 AI 回复的文本内容。

即使你目前只使用 DeepSeek，代码也已经为三种 provider 准备好了。`active_model: deepseek_chat` 时走 `provider == "deepseek"` 分支，其余分支暂时不执行——这不影响程序正确性。

### 检查点 7：运行并观察

从 `backend` 目录运行（注意带子目录路径）：

```powershell
python lecture\L1\lesson_01_chat.py
```

输入：

```text
你好
```

回复内容每次可能不同，但应类似：

```text
你：你好
deepseek：你好！有什么我可以帮助你的吗？
```

### 常见错误定位

| 错误或现象               | 所在层     | 处理方向                                         |
| ------------------------ | ---------- | ------------------------------------------------ |
| `can't open file`      | 文件层     | 检查工作目录、文件名、隐藏扩展名和零宽字符       |
| `ModuleNotFoundError`  | 环境层     | 检查`.venv`、解释器路径和 `pip install -e .` |
| YAML`ScannerError`     | 配置层     | 检查缩进、Tab、冒号后的空格                      |
| `KeyError: models`     | 配置层     | 检查 YAML 层级和键名                             |
| 未找到 API Key           | 秘密配置层 | 检查`.env` 位置与变量名                        |
| HTTP 401                 | API 层     | 密钥无效、平台不匹配或首尾空格                   |
| HTTP 402/余额错误        | 账户层     | 检查余额与计费状态                               |
| HTTP 404/model not found | API 层     | model ID 或 base URL 错误                        |
| 连接超时                 | 网络层     | 检查网络、代理、DNS 和 timeout                   |

### L1.1 小练习

1. 将问题改为"用一句话解释大语言模型"，观察结果。
2. 把 `temperature` 改为 `0`，连续询问相同问题两次。
3. 打印 `type(response)`，确认返回的不是普通字符串。
4. 故意把 YAML 的 `model` 改成不存在的值，观察错误后立即改回。
5. 用自己的话解释为什么 `config.yaml` 可以提交，而 `.env` 不可以。

### L1.1 验收

- [X] `python -m pip install -e .` 成功。
- [X] 依赖验证输出"依赖正常"。
- [X] YAML 验证能打印字典。
- [X] API Key 存在性验证输出 `True`，但没有打印真实值。
- [X] 输入"你好"能收到 DeepSeek 回复。
- [X] 能解释 `pyproject.toml`、`config.yaml`、`.env` 的职责。
- [X] 能说明当前程序为什么还不是 Agent。

完成这些检查后再进入 L1.2。

## L1.2 切换 DeepSeek、GPT 与本地 Ollama

### 学习目标

- 区分配置名、provider、API 地址、API Key 和 model ID。
- 看懂 `config.yaml` 如何通过 `active_model` 选择模型。
- 看懂 Python 代码如何根据 `provider` 字段自动选择正确的客户端类。
- 成功从 DeepSeek 切换到另一个模型（GPT 中转站或本地 Ollama）。
- 理解切换模型为什么只改 YAML 不动 Python 代码。

### 四个核心概念

以当前 `config.yaml` 为例：

```yaml
app:
  active_model: openai_proxy       # 指向下面 models 中的某个 key

models:
  openai_proxy:                    # ← 配置名：你自己起的，叫什么都可以
    provider: openai               # ← 决定用 ChatOpenAI 客户端
    model: gpt-5.5                 # ← API 真正接受的 model ID
    base_url: https://sapi.nyro.lol/v1  # ← 请求发到中转站而非 OpenAI 官方
    temperature: 0.2
```

- **配置名**（如 `openai_proxy`）：你自己起的别名，在 `active_model` 中引用。
- **provider**：决定程序创建 `ChatDeepSeek`、`ChatOpenAI` 还是 `ChatOllama`。
- **model**：API 真正接受的 model ID，不能随便编。必须与你用的服务商支持的 ID 一致。
- **base_url**：API 服务器地址。不写时程序自动用 provider 默认地址；写了就覆盖（中转站、自建服务等场景）。

API Key 不放在 YAML 中，仍然放在 `.env`。

### 三个客户端为什么不同

```text
DeepSeek → ChatDeepSeek → 需要 DEEPSEEK_API_KEY
OpenAI   → ChatOpenAI   → 需要 OPENAI_API_KEY（中转站也用这个）
Ollama   → ChatOllama   → 连接本机服务，通常不需要 Key
```

它们是不同的类，构造参数也不完全一样（Ollama 不需要 `api_key`，OpenAI 不需要 Ollama 格式的 `base_url`）。但创建完成后，调用方式完全一致：

```python
response = model.invoke("你好")
print(response.content)
```

这就是 `if/elif` 隔离的意义：创建时按 provider 区分，使用时统一接口。

### 用 YAML 选择模型：切换只改一行

```yaml
app:
  active_model: deepseek_chat    # 切到 DeepSeek
  # active_model: openai_proxy  # 切到中转站 GPT-5.5
  # active_model: ollama_local  # 切到本地 Ollama
```

Python 代码完全不动。

### 关于 API 中转站

如果你的 `config.yaml` 中有类似这样的配置：

```yaml
  openai_proxy:
    provider: openai
    model: gpt-5.5
    base_url: https://sapi.nyro.lol/v1    # 第三方中转地址
```

请求会发到中转站而不是 OpenAI 官方服务器。注意：

- `model` 按中转站提供的名称填写（如 `gpt-5.5`）。
- `.env` 中的 `OPENAI_API_KEY` 填中转站给你的密钥，不是 OpenAI 官方的。
- 只在你理解该服务的隐私、密钥和计费规则时使用。
- `base_url` 结尾需要 `/v1`，因为 LangChain 会在后面拼接 `/chat/completions`。

### 当前完整代码

完整代码就是 L1.1 中编写的那一份 [lesson_01_chat.py](lesson_01_chat.py)——它已经同时支持三种 provider，不需要额外文件。

代码结构回顾：

```text
定位 backend 目录（向上三级 Path.parent.parent.parent）
  -> 加载 backend/.env
  -> 加载 backend/config.yaml
  -> 读取 app.active_model → 取得对应模型配置
  -> 根据 provider 查表获取 API Key 和 base_url
  -> if/elif 创建对应客户端（ChatDeepSeek / ChatOpenAI / ChatOllama）
  -> 接收用户输入 → model.invoke() → 打印 response.content
```

### L1.2 练习

1. 先让 `active_model: deepseek_chat` 成功回复。
2. 如果你有中转站：在 config.yaml 加上 `openai_proxy` 段，`.env` 配好 `OPENAI_API_KEY`，切换 `active_model` 后运行。
3. 如果你有 Ollama：安装并启动，下载对应模型，切换到 `ollama_local` 运行。
4. 观察：无论切到哪个模型，`model.invoke(question)` 这行代码完全没变。

### 后续课程安排

第一课到这里就够了。更高级的话题安排在后续课程：

- L3：`BaseChatModel`、薄 model factory、`init_chat_model`。
- L5：不同 provider 的工具调用和结构化输出差异。
- L7：LangGraph 根据任务动态选择模型。
- L11：配置校验、统一错误处理和 provider 生命周期。
- L19：LiteLLM/模型网关、fallback、限流、成本和监控。

### L1.2 验收

- [X] 能区分配置名、provider、model ID 和 base_url。
- [X] 至少跑通一种 provider 并成功回复。
- [X] 所有普通参数来自 `config.yaml`。
- [X] 云端 API Key 只来自环境变量（`.env`）。
- [X] 能解释切换模型为什么只改 YAML 不需要改 Python 代码。
- [ ] 能解释中转站 base_url 为什么需要 `/v1` 后缀。

## L1.3 Windows、macOS、Linux 三端部署基础

本节只建立部署认知。真正制作安装包在 L19 完成。

### 开发环境为什么不能复制

虚拟环境包含解释器路径、平台脚本和可能的原生二进制，因此 `.venv` 不能从 Windows 复制到 macOS/Linux。源码和依赖声明可以共享，安装环境必须重新创建。

| 平台               | 创建环境                  | 激活环境                         |
| ------------------ | ------------------------- | -------------------------------- |
| Windows PowerShell | `python -m venv .venv`  | `.\.venv\Scripts\Activate.ps1` |
| macOS              | `python3 -m venv .venv` | `source .venv/bin/activate`    |
| Linux              | `python3 -m venv .venv` | `source .venv/bin/activate`    |

激活后统一执行：

```text
python -m pip install --upgrade pip
python -m pip install -e .
python lecture\L1\lesson_01_chat.py
```

### 生产构建流程

```text
Git 仓库中的同一份源码
  -> Windows runner -> PyInstaller 后端 -> electron-builder -> exe/msi
  -> macOS runner   -> PyInstaller 后端 -> electron-builder -> dmg/pkg
  -> Linux runner   -> PyInstaller 后端 -> electron-builder -> AppImage/deb
```

不要默认在 Windows 上可靠构建 macOS/Linux Python 二进制。包含 PyTorch、FAISS、tokenizers 等原生依赖时，更应在对应系统与 CPU 架构上构建。

### 三个平台的发布重点

| 平台    | 重点                                                      |
| ------- | --------------------------------------------------------- |
| Windows | 代码签名、杀毒软件误报、长路径与进程清理                  |
| macOS   | Developer ID、codesign、notarization、Intel/Apple Silicon |
| Linux   | glibc、桌面文件、权限、不同发行版验证                     |

### 从 L1 开始遵守的跨平台约束

- 路径使用 `pathlib.Path`，不写死 `C:\\...` 或 `/home/...`。
- 使用 `Path(__file__).resolve().parent...` 定位项目根目录，不依赖当前工作目录。
- 配置使用 UTF-8。
- 用户数据写入平台应用数据目录，不写入只读安装目录。
- `.env` 只用于开发；生产秘密进入操作系统凭据库。
- Python 服务未来只监听 `127.0.0.1`，并使用短期 token。
- Ollama 和大型模型默认不捆绑进基础安装包。

### L1.3 验收

- [X] 能解释为什么 `.venv` 不能跨系统复制。
- [X] 能说出三个平台的典型安装包。
- [ ] 能解释 macOS 为什么多一步 notarization。
- [X] 能说明为什么三平台应分别构建并在干净系统测试。
- [X] 能指出当前代码中哪些写法已经具备跨平台性。

## L1 总验收

只有以下项目全部完成，才进入 L2：

- [X] 至少一种 provider 单轮问答成功。
- [X] 所有普通参数位于 `config.yaml`。
- [X] 所有秘密位于 `.env` 或系统环境变量。
- [X] 能解释一次模型调用的完整链路（键盘输入 → response.content）。
- [X] 能解释三端开发与生产构建的差异。

## 参考资料

- [DeepSeek API 文档](https://api-docs.deepseek.com/)
- [OpenAI 模型文档](https://platform.openai.com/docs/models)
- [Ollama 文档](https://docs.ollama.com/)
- [LangChain ChatDeepSeek](https://docs.langchain.com/oss/python/integrations/chat/deepseek)
- [LangChain ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai)
- [LangChain ChatOllama](https://docs.langchain.com/oss/python/integrations/chat/ollama)
