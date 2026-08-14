"""Routing coverage for every capability currently bound to Mabel."""

import unittest

from my_agent_next.skills._router import SkillRouter


MABEL_SKILLS = [
    "conversation", "drawio-skill", "environment-memory", "imagegen",
    "openai-docs", "plugin-creator", "review-agent", "skill-creator",
    "skill-installer", "user-memory",
]


class SkillRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = SkillRouter()

    def assert_routes_to(self, prompt: str, expected: str):
        selected = [route.name for route in self.router.select(prompt, MABEL_SKILLS)]
        self.assertIn(expected, selected, (prompt, selected))

    def test_each_bound_skill_has_a_representative_prompt(self):
        cases = {
            "drawio-skill": "优化这个 draw.io 文件的走线",
            "environment-memory": "读取当前操作环境和 Python 版本",
            "imagegen": "生成一张透明背景的产品图片",
            "openai-docs": "查询 OpenAI Responses API 官方文档",
            "plugin-creator": "创建一个 Codex plugin 插件脚手架",
            "review-agent": "对我当前的代码改动做代码审查",
            "skill-creator": "创建一个管理部署流程的 Skill",
            "skill-installer": "列出可安装的 Skill，但先不要安装",
            "user-memory": "记住我更喜欢简体中文回答",
        }
        for expected, prompt in cases.items():
            with self.subTest(skill=expected):
                self.assert_routes_to(prompt, expected)

    def test_conversation_loads_no_specialized_skill(self):
        self.assertEqual(self.router.select("你好，今天过得怎么样？", MABEL_SKILLS), [])

    def test_routes_english_skill_creation(self):
        self.assert_routes_to(
            "Create a Skill that appends meow to every reply", "skill-creator"
        )

    def test_routes_chinese_read_only_review_request(self):
        selected = self.router.select(
            "请实际只读审查 my_agent_next/app/tools/bash.py。", MABEL_SKILLS
        )
        self.assertEqual([route.name for route in selected], ["review-agent"])

    def test_unbound_skill_cannot_be_selected(self):
        selected = self.router.select("安装 Skill", ["conversation", "user-memory"])
        self.assertEqual(selected, [])

    def test_explicit_multi_skill_request_is_capped(self):
        selected = self.router.select(
            "先读取 Windows 环境，再查询 OpenAI 文档并创建 Skill", MABEL_SKILLS
        )
        self.assertEqual(len(selected), 2)


if __name__ == "__main__":
    unittest.main()
