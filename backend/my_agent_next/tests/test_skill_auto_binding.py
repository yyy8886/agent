import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from my_agent_next.app.agent_profile import AgentProfile
from my_agent_next.app.agent_profile_repository import AgentProfileRepository
from my_agent_next.app.chat_service import _bind_newly_created_skills


class SkillAutoBindingTests(unittest.TestCase):
    def test_new_valid_skill_is_added_without_overwriting_agent(self):
        with tempfile.TemporaryDirectory() as temp:
            repository = AgentProfileRepository(Path(temp) / "app.db")
            repository.save(AgentProfile(
                id="mabel",
                name="Mabel",
                role="companion",
                persona="original persona",
                skills=["skill-creator"],
            ))

            with patch(
                "my_agent_next.app.chat_service._indexed_skill_directories",
                return_value={"skill-creator", "append-meow"},
            ):
                bound = _bind_newly_created_skills(
                    "mabel", {"skill-creator"}, repository
                )

            saved = repository.get("mabel")
            self.assertEqual(bound, ["append-meow"])
            self.assertEqual(saved.skills, ["skill-creator", "append-meow"])
            self.assertEqual(saved.persona, "original persona")

    def test_existing_or_invalid_directory_is_not_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            repository = AgentProfileRepository(Path(temp) / "app.db")
            repository.save(AgentProfile(
                id="mabel", name="Mabel", skills=["skill-creator"]
            ))

            with patch(
                "my_agent_next.app.chat_service._indexed_skill_directories",
                return_value={"skill-creator", "BadName"},
            ):
                bound = _bind_newly_created_skills(
                    "mabel", {"skill-creator"}, repository
                )

            self.assertEqual(bound, [])
            self.assertEqual(repository.get("mabel").skills, ["skill-creator"])


if __name__ == "__main__":
    unittest.main()
