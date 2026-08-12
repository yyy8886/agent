# test_api_profile_service.py — 单元测试
# =============================================================================
# 测试 ApiProfileService 的核心用例：CRUD + 默认配置保护。
#
# 每个测试使用临时 SQLite 数据库（tempfile），互不干扰。
# 覆盖场景：
#   test_crud_and_default        → 增删改查 + 设为默认 + 不可删除默认
#   test_rejects_invalid_remote_key_setting → 远程 provider 缺 api_key_env 应抛出异常
#
# 运行方式：
#   python -m pytest backend/my_agent_next/tests/test_api_profile_service.py -v"""

import tempfile
import unittest
from pathlib import Path

from my_agent_next.app.api_profile_repository import ApiProfileRepository
from my_agent_next.app.api_profile_service import ApiProfileService


class ApiProfileServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        repository = ApiProfileRepository(Path(self.temp.name) / "test.db")
        self.service = ApiProfileService(repository)

    def tearDown(self):
        self.temp.cleanup()

    def test_crud_and_default(self):
        payload = {"id":"local_test","name":"Local","provider":"ollama","model":"qwen","base_url":"http://127.0.0.1:11434"}
        self.service.save(payload)
        self.assertEqual(len(self.service.list()), 1)
        self.assertTrue(self.service.set_default("local_test")["is_default"])
        with self.assertRaises(ValueError):
            self.service.delete("local_test")

    def test_rejects_invalid_remote_key_setting(self):
        with self.assertRaises(ValueError):
            self.service.save({"id":"bad_remote","name":"Bad","provider":"openai","model":"gpt","base_url":"https://example.com"})


if __name__ == "__main__":
    unittest.main()

