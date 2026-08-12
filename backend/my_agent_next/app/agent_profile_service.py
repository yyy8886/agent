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
        """返回所有已使用过的 Skill 名称，供前端建议。

        注意：my_agent_next 的 Skill 目前只是字符串标签——还没有像 my_agent
        那样的 skill_manager / SKILL.md 执行引擎。这里从已有 Agent 的 skills
        字段中汇总出所有出现过的名称，省去重复输入。后续实现 Skill 引擎后，
        会改为从 registry.json 动态读取。"""
        seen: set[str] = set()
        for agent in AgentProfileRepository().list():
            for skill in agent.skills:
                seen.add(skill)
        return [{"name": name} for name in sorted(seen)]

    @staticmethod
    def model_options() -> list[dict]:
        """返回启用的 API Profile 列表，供前端下拉框选择模型。"""
        repo = ApiProfileRepository()
        return [
            {"id": p.id, "name": p.name, "provider": p.provider, "model": p.model}
            for p in repo.list() if p.enabled
        ]
