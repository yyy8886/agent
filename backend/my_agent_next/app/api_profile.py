# api_profile.py — 领域模型与校验规则
# =============================================================================
# 本文件是项目的"数据根基"，定义了 ApiProfile 这个核心数据结构。
#
# 职责：
#   1. 用 dataclass 定义模型 API 配置的所有字段（id / provider / model / base_url / ...）
#   2. validate()   — 逐字段校验（ID 格式、provider 合法性、temperature 范围等）
#   3. to_dict()    — 将对象序列化为字典（供 API 返回给前端）
#   4. from_dict()  — 从字典反序列化为对象（供 API 接收前端提交的数据）
#
# 项目中的位置：
#   前端提交 JSON → web_server.py 接收 → ApiProfileService.save()
#   → ApiProfile.from_dict(payload)  ← 在这里
#   → ApiProfile.validate()         ← 在这里
#   → ApiProfileRepository.save()   → SQLite 持久化"""

from dataclasses import asdict, dataclass
import re


ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,50}$")
ENV_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
SUPPORTED_PROVIDERS = {"openai", "deepseek", "ollama"}


@dataclass(slots=True)
class ApiProfile:
    id: str
    name: str
    provider: str
    model: str
    base_url: str
    api_key_env: str | None = None
    temperature: float = 0.2
    timeout_seconds: int = 60
    max_retries: int = 2
    enabled: bool = True
    is_default: bool = False

    def validate(self) -> None:
        if not ID_PATTERN.fullmatch(self.id):
            raise ValueError("配置 ID 必须以小写字母开头，只能包含小写字母、数字、下划线和连字符。")
        if not self.name.strip():
            raise ValueError("显示名称不能为空。")
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"不支持的 provider：{self.provider}")
        if not self.model.strip():
            raise ValueError("模型名称不能为空。")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature 必须在 0 到 2 之间。")
        if not 1 <= self.timeout_seconds <= 600:
            raise ValueError("timeout_seconds 必须在 1 到 600 之间。")
        if not 0 <= self.max_retries <= 10:
            raise ValueError("max_retries 必须在 0 到 10 之间。")
        if self.provider == "ollama":
            self.api_key_env = None
        elif not self.api_key_env or not ENV_PATTERN.fullmatch(self.api_key_env):
            raise ValueError("远程 provider 必须配置有效的 API Key 环境变量名。")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ApiProfile":
        profile = cls(
            id=str(data["id"]).strip(),
            name=str(data["name"]).strip(),
            provider=str(data["provider"]).strip().lower(),
            model=str(data["model"]).strip(),
            base_url=str(data.get("base_url", "")).strip(),
            api_key_env=(str(data["api_key_env"]).strip() if data.get("api_key_env") else None),
            temperature=float(data.get("temperature", 0.2)),
            timeout_seconds=int(data.get("timeout_seconds", 60)),
            max_retries=int(data.get("max_retries", 2)),
            enabled=bool(data.get("enabled", True)),
            is_default=bool(data.get("is_default", False)),
        )
        profile.validate()
        return profile

