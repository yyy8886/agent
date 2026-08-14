import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from my_agent_next.skills._loader import (
    INDEX_VERSION,
    available_skill_choices,
    ensure_index,
    rebuild_index,
)


def write_skill(root: Path, directory: str, name: str, description: str) -> None:
    target = root / directory
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


class SkillIndexTests(unittest.TestCase):
    def test_choices_use_directory_as_binding_key_and_frontmatter_as_display_name(self):
        index = {
            "skills": [{
                "directory": "miao-qids",
                "name": "MiaoQIDS",
                "description": "Miao QIDS tools",
            }]
        }
        with patch("my_agent_next.skills._loader.ensure_index", return_value=index):
            self.assertEqual(
                available_skill_choices(),
                [{
                    "name": "miao-qids",
                    "display_name": "MiaoQIDS",
                    "description": "Miao QIDS tools",
                }],
            )

    def test_rebuild_persists_metadata_without_body(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_skill(root, "sample", "sample", "Sample description")
            data = rebuild_index(root)
            stored = json.loads((root / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(stored, data)
            self.assertEqual(data["version"], INDEX_VERSION)
            self.assertNotIn("content", data["skills"][0])

    def test_ensure_index_refreshes_changed_added_and_removed_skills(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_skill(root, "first", "first", "Before")
            before = ensure_index(root)
            write_skill(root, "second", "second", "New")
            (root / "first" / "SKILL.md").write_text(
                "---\nname: first\ndescription: After\n---\n\n# First\n",
                encoding="utf-8",
            )
            after = ensure_index(root)
            self.assertNotEqual(before, after)
            self.assertEqual(
                [(item["name"], item["description"]) for item in after["skills"]],
                [("first", "After"), ("second", "New")],
            )
            (root / "second" / "SKILL.md").unlink()
            removed = ensure_index(root)
            self.assertEqual([item["name"] for item in removed["skills"]], ["first"])

    def test_corrupt_index_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_skill(root, "sample", "sample", "Valid")
            (root / "index.json").write_text("not json", encoding="utf-8")
            data = ensure_index(root)
            self.assertEqual(data["skills"][0]["name"], "sample")


if __name__ == "__main__":
    unittest.main()
