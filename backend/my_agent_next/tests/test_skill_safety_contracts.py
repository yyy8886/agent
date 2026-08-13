"""Regression tests for safety rules learned from real Skill runs."""

import unittest
from pathlib import Path

from my_agent_next.app.chat_service import _is_valid_review_response, _tool_names_for_skills


SKILLS = Path(__file__).resolve().parent.parent / "skills"


class SkillSafetyContractTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")

    def test_review_requires_change_behavior_and_impact_evidence(self):
        text = self.read("review-agent")
        self.assertIn("Change evidence", text)
        self.assertIn("Behavior evidence", text)
        self.assertIn("Impact evidence", text)
        self.assertIn("A file path by itself is not a change boundary", text)

    def test_creator_cannot_modify_itself_or_dependencies(self):
        text = self.read("skill-creator")
        self.assertIn("only writable scope", text)
        self.assertIn("Never modify this `skill-creator` Skill", text)
        self.assertIn("Do not patch the dependency", text)

    def test_installer_stops_when_official_sources_fail(self):
        text = self.read("skill-installer")
        self.assertIn("If every direct official source fails, stop", text)
        self.assertIn("Do not use search-engine snippets", text)
        self.assertIn("do not fall back to third-party search", text)

    def test_review_tool_allowlist_is_enforced(self):
        allowed = _tool_names_for_skills(["review-agent"])
        self.assertEqual(allowed, {"read_file", "grep", "glob"})
        self.assertNotIn("write_file", allowed)
        self.assertNotIn("edit_file", allowed)
        self.assertNotIn("run_bash", allowed)

    def test_review_output_contract_is_enforced(self):
        valid = (
            "[P2] Handle the failing branch — app/service.py:42\n\n"
            "The demonstrated input returns the wrong value.\n\n"
            "Overall assessment: The change needs one correction.\n"
            "Test gaps or residual risks: The platform branch remains untested."
        )
        self.assertTrue(_is_valid_review_response(valid))
        self.assertTrue(_is_valid_review_response(
            "No findings.\n\nOverall assessment: The target looks correct.\n"
            "Test gaps or residual risks: No runtime test was supplied."
        ))
        self.assertFalse(_is_valid_review_response("## Overall assessment\nNo findings."))
        self.assertFalse(_is_valid_review_response("[P1] Missing location"))


if __name__ == "__main__":
    unittest.main()
