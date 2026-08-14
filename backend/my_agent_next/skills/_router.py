"""Deterministic, allowlist-first routing for installed Skills."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._loader import get


@dataclass(frozen=True)
class SkillRoute:
    name: str
    reason: str


# Routing hints are deliberately separate from SKILL.md. They are application-level
# dispatch policy, while Agent bindings remain the authorization boundary.
ROUTING_HINTS: dict[str, tuple[str, ...]] = {
    "address-lookup": ("地址查询", "地址定位", "ip定位", "ip 定位", "公网ip", "公网 ip", "我在哪", "当前位置", "本机位置", "经纬度", "address-lookup"),
    "drawio-skill": ("draw.io", "drawio", "流程图", "架构图", "时序图", "走线", "拓扑图"),
    "environment-memory": ("运行环境", "操作环境", "环境变量", "python版本", "python 版本", "windows", "linux", "wsl", "shell", "部署环境"),
    "imagegen": ("生成图片", "生成图像", "画一张", "图片生成", "编辑图片", "修改图片", "透明背景", "imagegen"),
    "openai-docs": ("openai", "chatgpt", "codex", "responses api", "realtime api", "模型价格", "模型迁移"),
    "plugin-creator": ("创建插件", "新建插件", "插件脚手架", "plugin.json", "codex plugin"),
    "review-agent": (
        "代码审查", "审查代码", "审查改动", "只读审查", "review代码",
        "review code", "review-agent", "检查这个diff", "检查 diff",
    ),
    "skill-creator": (
        "创建skill", "创建一个skill", "新建skill", "修改skill", "更新skill", "编写skill",
        "create a skill", "create skill", "new skill", "update skill", "edit skill",
    ),
    "skill-installer": ("安装skill", "可安装的skill", "可安装skill", "从github安装", "skill市场"),
    "user-memory": ("记住我", "记住这个", "我的偏好", "我叫什么", "忘掉我", "删除记忆", "用户记忆"),
}


class SkillRouter:
    """Select relevant Skills from an Agent's existing binding allowlist."""

    def __init__(self, max_selected: int = 2):
        self.max_selected = max_selected

    def select(self, user_message: str, bound_skills: list[str]) -> list[SkillRoute]:
        normalized = re.sub(r"\s+", " ", user_message.casefold()).strip()
        compact = re.sub(r"\s+", "", normalized)
        matches: list[tuple[int, int, SkillRoute]] = []

        for order, name in enumerate(bound_skills):
            if name == "conversation" or get(name) is None:
                continue
            hints = ROUTING_HINTS.get(name, ())
            matched = [
                hint for hint in hints
                if re.sub(r"\s+", "", hint.casefold()) in compact
            ]
            if name == "skill-creator" and "skill" in compact and any(
                action in compact
                for action in (
                    "创建", "新建", "编写", "修改", "更新",
                    "create", "new", "write", "edit", "update",
                )
            ):
                matched.append("创建/修改 + Skill")
            if name == "skill-installer" and "skill" in compact and any(
                action in compact for action in ("安装", "可安装", "市场", "下载")
            ):
                matched.append("安装/市场 + Skill")
            explicit = name.casefold() in normalized
            if not matched and not explicit:
                continue
            score = (100 if explicit else 0) + max((len(item) for item in matched), default=0)
            reason = f"用户明确提到 {name}" if explicit else f"匹配：{max(matched, key=len)}"
            matches.append((-score, order, SkillRoute(name=name, reason=reason)))

        matches.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in matches[: self.max_selected]]


def build_skill_catalog(bound_skills: list[str]) -> str:
    """Build compact metadata for authorized Skills without loading their bodies."""
    lines = []
    for name in bound_skills:
        info = get(name)
        if info:
            lines.append(f"- {info.name}: {info.description}")
    return "\n".join(lines)
