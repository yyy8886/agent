import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from my_agent_next.app.skill_compatibility import (
    SkillCompatibilityRepository, compatibility_status, scan_skill, skill_fingerprint,
)


def write_skill(root: Path, name: str, body: str = "# Rules\nReply clearly.") -> Path:
    target = root / name
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill\n---\n\n{body}\n", encoding="utf-8"
    )
    return target


class SkillCompatibilityTests(unittest.TestCase):
    def test_plain_instruction_skill_is_green(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skills"
            target = write_skill(root, "plain-skill")
            repository = SkillCompatibilityRepository(Path(temp) / "app.db")
            report = scan_skill("plain-skill", skills_dir=root, repository=repository)
            self.assertEqual(report["level"], "green")
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["skill_fingerprint"], skill_fingerprint(target))

    def test_platform_specific_missing_command_is_not_green(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skills"
            write_skill(root, "codex-only", "Use $CODEX_HOME and drawio to export.")
            repository = SkillCompatibilityRepository(Path(temp) / "app.db")
            with patch("my_agent_next.app.skill_compatibility.shutil.which", return_value=None):
                report = scan_skill("codex-only", skills_dir=root, repository=repository)
            self.assertIn(report["level"], {"yellow", "red"})
            self.assertEqual(
                {issue["code"] for issue in report["issues"]},
                {"platform_specific", "missing_command"},
            )

    def test_urls_and_documentation_path_examples_do_not_reduce_compatibility(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skills"
            write_skill(
                root, "documented-paths",
                "Never use $CODEX_HOME or ~/.codex. See https://example.com/home/test. "
                "Do not convert C:\\work to /mnt/c/work manually.",
            )
            repository = SkillCompatibilityRepository(Path(temp) / "app.db")
            report = scan_skill("documented-paths", skills_dir=root, repository=repository)
            self.assertEqual(report["level"], "green")
            self.assertEqual(report["issues"], [])

    def test_codex_plugin_contract_remains_partial_compatibility(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skills"
            write_skill(root, "plugin-maker", "Create .codex-plugin/plugin.json.")
            repository = SkillCompatibilityRepository(Path(temp) / "app.db")
            report = scan_skill("plugin-maker", skills_dir=root, repository=repository)
            self.assertEqual(report["level"], "yellow")
            self.assertEqual(report["issues"][0]["code"], "platform_specific")

    def test_uri_and_docker_volume_fragments_are_not_windows_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skills"
            target = write_skill(root, "path-fragments")
            scripts = target / "scripts"
            scripts.mkdir()
            (scripts / "parse.py").write_text(
                "examples = ['https://example.test', 'db:/web/db', 'vol:/path']\n",
                encoding="utf-8",
            )
            repository = SkillCompatibilityRepository(Path(temp) / "app.db")
            report = scan_skill("path-fragments", skills_dir=root, repository=repository)
            self.assertEqual(report["level"], "green")

    def test_powershell_aliases_are_alternatives(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skills"
            target = write_skill(root, "shell-choice")
            scripts = target / "scripts"
            scripts.mkdir()
            (scripts / "check.py").write_text(
                "commands = ['pwsh', 'powershell']\n", encoding="utf-8"
            )
            repository = SkillCompatibilityRepository(Path(temp) / "app.db")
            with patch(
                "my_agent_next.app.skill_compatibility.shutil.which",
                side_effect=lambda command: "found" if command == "powershell" else None,
            ):
                report = scan_skill("shell-choice", skills_dir=root, repository=repository)
            self.assertEqual(report["level"], "green")

    def test_manual_script_edit_marks_cached_report_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skills"
            target = write_skill(root, "editable-skill")
            repository = SkillCompatibilityRepository(Path(temp) / "app.db")
            scan_skill("editable-skill", skills_dir=root, repository=repository)
            self.assertEqual(compatibility_status("editable-skill", root, repository)["status"], "ready")
            scripts = target / "scripts"
            scripts.mkdir()
            (scripts / "run.py").write_text("print('changed')\n", encoding="utf-8")
            self.assertEqual(compatibility_status("editable-skill", root, repository)["status"], "stale")


if __name__ == "__main__":
    unittest.main()
