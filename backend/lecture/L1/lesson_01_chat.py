# L1 — 首次模型调用
# 本课独有：model.invoke("字符串") — 最简单的一次问答，无历史、无模板、无链。
# 从这里开始：config.yaml 选模型 → .env 读密钥 → 创建客户端 → invoke → 打印。
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
