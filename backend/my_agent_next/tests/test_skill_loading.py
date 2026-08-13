"""Verify ChatService injects metadata broadly and Skill bodies narrowly."""

import unittest
from unittest.mock import patch

from my_agent_next.app.chat_service import ChatService


class _Agent:
    name = "梅贝尔"
    persona = "测试人格"
    skills = ["conversation", "environment-memory", "drawio-skill", "imagegen"]


class _Repository:
    def get_thread(self, _thread_id):
        return {}

    def get_messages(self, _thread_id, limit):
        return []


class SkillLoadingTests(unittest.TestCase):
    @patch("my_agent_next.app.chat_service.AgentProfileRepository.get", return_value=_Agent())
    def test_environment_request_loads_only_environment_body(self, _get):
        messages = ChatService(_Repository()).build_messages(
            "mabel", "thread", "读取当前 Windows 运行环境"
        )
        system_text = "\n".join(
            message.content for message in messages if message.type == "system"
        )
        self.assertIn("## 已授权 Skill 目录", system_text)
        self.assertIn("## 本轮已加载 Skill：environment-memory", system_text)
        self.assertNotIn("## 本轮已加载 Skill：drawio-skill", system_text)
        self.assertNotIn("## 本轮已加载 Skill：imagegen", system_text)

    @patch("my_agent_next.app.chat_service.AgentProfileRepository.get", return_value=_Agent())
    def test_conversation_request_loads_no_skill_body(self, _get):
        messages = ChatService(_Repository()).build_messages(
            "mabel", "thread", "你好，陪我聊聊天"
        )
        system_text = "\n".join(
            message.content for message in messages if message.type == "system"
        )
        self.assertIn("## 已授权 Skill 目录", system_text)
        self.assertNotIn("## 本轮已加载 Skill：", system_text)


if __name__ == "__main__":
    unittest.main()
