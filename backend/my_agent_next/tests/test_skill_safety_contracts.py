"""Regression tests for safety rules learned from real Skill runs."""

import unittest
import importlib.util
import sys
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

    def test_creator_defaults_to_application_skill_directory(self):
        text = self.read("skill-creator")
        self.assertIn("default destination", text)
        self.assertIn("`skills/<skill-name>/`", text)
        self.assertIn("never default to\n`$CODEX_HOME/skills`", text)
        self.assertIn("not from the process working directory", text)

    def test_creator_is_written_for_the_application_not_global_codex(self):
        text = self.read("skill-creator")
        self.assertIn("extend this application", text)
        self.assertNotIn("Mabel", text)
        self.assertNotIn("extend Codex's capabilities", text)

    def test_installer_stops_when_official_sources_fail(self):
        text = self.read("skill-installer")
        self.assertIn("If every direct official source fails, stop", text)
        self.assertIn("Do not use search-engine snippets", text)
        self.assertIn("do not fall back to third-party search", text)

    def test_installer_defaults_to_the_application_skill_directory(self):
        scripts = SKILLS / "skill-installer" / "scripts"
        sys.path.insert(0, str(scripts))
        try:
            installer_spec = importlib.util.spec_from_file_location(
                "project_skill_installer", scripts / "install-skill-from-github.py"
            )
            installer = importlib.util.module_from_spec(installer_spec)
            sys.modules[installer_spec.name] = installer
            installer_spec.loader.exec_module(installer)
            listing_spec = importlib.util.spec_from_file_location(
                "project_skill_listing", scripts / "list-skills.py"
            )
            listing = importlib.util.module_from_spec(listing_spec)
            sys.modules[listing_spec.name] = listing
            listing_spec.loader.exec_module(listing)
        finally:
            sys.path.pop(0)
            sys.modules.pop("project_skill_installer", None)
            sys.modules.pop("project_skill_listing", None)
        expected = str(SKILLS.resolve())
        self.assertEqual(installer._default_dest(), expected)
        self.assertEqual(listing._project_skills_dir(), expected)

    def test_imagegen_uses_its_project_local_chroma_key_helper(self):
        text = self.read("imagegen")
        self.assertIn("scripts/remove_chroma_key.py", text)
        self.assertNotIn("$CODEX_HOME/skills/.system/imagegen", text)

    def test_imagegen_references_use_project_local_paths(self):
        imagegen = SKILLS / "imagegen"
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in imagegen.rglob("*.md")
        )
        self.assertIn("references/network.md", text)
        self.assertNotIn("$CODEX_HOME", text)
        self.assertNotIn("~/.codex", text)

    def test_environment_memory_is_not_bound_to_a_specific_agent_name(self):
        text = self.read("environment-memory")
        self.assertIn("this application's current runtime environment", text)
        self.assertNotIn("for Mabel", text)

    def test_system_time_metadata_is_not_bound_to_a_specific_agent_name(self):
        text = self.read("system-time")
        self.assertIn('"author":"this application"', text)
        self.assertNotIn("Mabel", text)

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
