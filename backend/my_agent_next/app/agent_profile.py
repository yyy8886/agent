# agent_profile.py — Agent 领域模型与校验规则
# =============================================================================
# 本文件定义 AgentProfile：一个 Agent 的完整配置（角色设定、绑定模型、可用 Skill）。
#
# 字段说明：
#   id               — 唯一标识（如 "mabel"、"analyst"）
#   name             — 显示名称（如 "梅贝尔"、"分析师"）
#   role             — 角色描述（如 "陪伴者与最终输出"）
#   persona          — 系统提示词 / 人设（直接传给 LLM 的 system prompt）
#   model_profile_id — 使用的 API 配置 ID（外键 → api_profiles 表）
#   skills           — 该 Agent 可用的 Skill 名称列表
#   enabled          — 是否启用
#
# 项目中的位置（与 ApiProfile 平行）：
#   前端表单 → web_server.py → AgentProfileService → AgentProfileRepository → agents 表"""

import re
from dataclasses import asdict, dataclass, field


ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")
SKILL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")


@dataclass(slots=True)
class AgentProfile:
    id: str
    name: str
    role: str = ""
    persona: str = ""
    model_profile_id: str = ""
    skills: list[str] = field(default_factory=list)
    enabled: bool = True

    def validate(self) -> None:
        if not ID_PATTERN.fullmatch(self.id):
            raise ValueError("Agent ID 必须以小写字母开头，只能包含小写字母、数字、下划线和连字符，最长 40 字符。")
        if not self.name.strip():
            raise ValueError("Agent 名称不能为空。")
        for skill in self.skills:
            if not SKILL_NAME_PATTERN.fullmatch(skill):
                raise ValueError(f"无效的 Skill 名称：{skill}")
        if self.model_profile_id and not ID_PATTERN.fullmatch(self.model_profile_id):
            raise ValueError(f"无效的模型配置 ID：{self.model_profile_id}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentProfile":
        profile = cls(
            id=str(data["id"]).strip(),
            name=str(data["name"]).strip(),
            role=str(data.get("role", "")).strip(),
            persona=str(data.get("persona", "")).strip(),
            model_profile_id=str(data.get("model_profile_id", "")).strip(),
            skills=[str(s).strip() for s in data.get("skills", []) if str(s).strip()],
            enabled=bool(data.get("enabled", True)),
        )
        profile.validate()
        return profile
