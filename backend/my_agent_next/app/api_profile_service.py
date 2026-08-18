# api_profile_service.py — 业务逻辑层（用例 / Service）
# =============================================================================
# 本文件是"业务逻辑层"，在持久化层（Repository）和接口层（web_server.py）之间。
# 它不是单纯透传——它包含领域规则，比如"不能删除默认配置"。
#
# 职责：
#   1. list()        — 列出所有配置，返回脱敏后的公开数据（不含真实 Key）
#   2. save(payload) — 从字典创建 ApiProfile → 校验 → 存入数据库
#   3. delete(id)    — 删除配置（禁止删除默认配置）
#   4. set_default() — 切换默认配置
#   5. _public()     — 将 ApiProfile 转为前端友好的 dict，附加 api_key_configured 字段
#
# 项目中的位置（三层架构）：
#   web_server.py (接口层) → ApiProfileService (业务层) → ApiProfileRepository (数据层)
#   HTTP 请求/响应           → 用例逻辑/校验            → SQLite 读写"""

import os
from pathlib import Path
import re

from dotenv import set_key

from .runtime_paths import ENV_FILE

from .api_profile import ApiProfile
from .api_profile_repository import ApiProfileRepository


class ApiProfileService:
    def __init__(
        self,
        repository: ApiProfileRepository | None = None,
        env_path: Path | None = None,
    ):
        self.repository = repository or ApiProfileRepository()
        self.env_path = env_path or ENV_FILE

    def list(self) -> list[dict]:
        return [self._public(profile) for profile in self.repository.list()]

    def save(self, payload: dict) -> dict:
        payload = dict(payload)
        secret = payload.pop("api_key", None)
        profile_id = str(payload.get("id", "")).strip()
        existing = self.repository.get(profile_id)
        if str(payload.get("provider", "")).strip().lower() != "ollama":
            payload["api_key_env"] = (
                existing.api_key_env if existing and existing.api_key_env
                else self._env_name(profile_id)
            )
            if not secret and not existing:
                raise ValueError("远程 provider 必须填写 API Key。")
            if secret:
                self._write_env(payload["api_key_env"], str(secret))
        else:
            payload["api_key_env"] = None
        profile = ApiProfile.from_dict(payload)
        existing = self.repository.get(profile.id)
        if existing and "is_default" not in payload:
            profile.is_default = existing.is_default
        self.repository.save(profile)
        return self._public(profile)

    @staticmethod
    def _env_name(profile_id: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", profile_id).strip("_").upper()
        return f"MY_AGENT_{normalized}_API_KEY"

    def _write_env(self, name: str, value: str) -> None:
        set_key(self.env_path, name, value, quote_mode="always")
        os.environ[name] = value

    def delete(self, profile_id: str) -> bool:
        existing = self.repository.get(profile_id)
        if existing and existing.is_default:
            raise ValueError("不能删除默认配置，请先设置另一个默认配置。")
        return self.repository.delete(profile_id)

    def set_default(self, profile_id: str) -> dict:
        self.repository.set_default(profile_id)
        profile = self.repository.get(profile_id)
        return self._public(profile)

    @staticmethod
    def _public(profile: ApiProfile) -> dict:
        data = profile.to_dict()
        data["api_key_configured"] = (
            True if profile.provider == "ollama" else bool(os.getenv(profile.api_key_env or ""))
        )
        return data
