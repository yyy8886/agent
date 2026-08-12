from __future__ import annotations

# agent_profile_service.py — Agent 业务逻辑层
# =============================================================================
# 本文件处理 Agent 配置的 CRUD 用例，与 ApiProfileService 平行。
#
# 职责：
#   1. list()    — 列出所有 Agent
#   2. save()    — 新增或更新 Agent（含校验）
#   3. delete()  — 删除 Agent
#   4. available_skills() — 返回所有可用的 Skill 名称列表（从内置注册表读取）
#   5. model_options()    — 返回可选的 API Profile 列表（供前端下拉框使用）
#
# 项目中的位置（三层架构）：
#   web_server.py → AgentProfileService → AgentProfileRepository → agents 表"""

from .agent_profile import AgentProfile
from .agent_profile_repository import AgentProfileRepository
from .api_profile_repository import ApiProfileRepository


class AgentProfileService:
    def __init__(self, repository: AgentProfileRepository | None = None):
        self.repository = repository or AgentProfileRepository()

    def list(self) -> list[dict]:
        return [p.to_dict() for p in self.repository.list()]

    def save(self, payload: dict) -> dict:
        profile = AgentProfile.from_dict(payload)
        self.repository.save(profile)
        return profile.to_dict()

    def delete(self, agent_id: str) -> bool:
        return self.repository.delete(agent_id)

    @staticmethod
    def available_skills() -> list[dict]:
        """从 skills/ 目录扫描所有 SKILL.md，返回 {name, description}。"""
        from my_agent_next.skills._loader import available_skill_choices
        return available_skill_choices()

    @staticmethod
    def model_options() -> list[dict]:
        """返回启用的 API Profile 列表，供前端下拉框选择模型。"""
        repo = ApiProfileRepository()
        return [
            {"id": p.id, "name": p.name, "provider": p.provider, "model": p.model}
            for p in repo.list() if p.enabled
        ]
