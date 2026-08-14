import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from my_agent_next.app import marketplace_api


class ClawHubMarketplaceTests(unittest.TestCase):
    def test_preview_uses_bare_slug_even_when_owner_is_present(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "skill": {
                "slug": "miao-qids",
                "summary": "PCAP analyzer",
                "description": "---\nname: miao-qids\ndescription: test\n---\nBody",
            }
        }
        with patch.object(marketplace_api._client, "get", return_value=response) as get:
            detail = marketplace_api._get_clawhub_skill(
                "miao-qids", owner_handle="tsherryyann"
            )
        self.assertEqual(
            get.call_args.args[0],
            f"{marketplace_api.CLAWHUB_BASE}/skills/miao-qids",
        )
        self.assertEqual(detail["name"], "miao-qids")
        self.assertTrue(detail["content"].startswith("---"))

    def test_download_extracts_files_and_blocks_zip_traversal(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("SKILL.md", "---\nname: miao-qids\ndescription: test\n---\n")
            archive.writestr("scripts/run.py", "print('ok')\n")
            archive.writestr("../outside.txt", "blocked")
        response = Mock(status_code=200, content=payload.getvalue())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skills"
            with patch.object(marketplace_api, "SKILLS_DIR", root), patch.object(
                marketplace_api._client, "get", return_value=response
            ):
                count = marketplace_api._download_and_extract_clawhub(
                    "miao-qids", "miao-qids"
                )
            self.assertEqual(count, 2)
            self.assertTrue((root / "miao-qids" / "SKILL.md").is_file())
            self.assertTrue((root / "miao-qids" / "scripts" / "run.py").is_file())
            self.assertFalse((root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
