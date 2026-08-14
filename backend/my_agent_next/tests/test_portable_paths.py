import ast
import re
import unittest
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
PACKAGE = BACKEND / "my_agent_next"


class PortablePathTests(unittest.TestCase):
    def test_check_models_resolves_env_from_script_location(self):
        source = (BACKEND / "check_models.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertIn('Path(__file__).resolve().parent / "my_agent_next"', source)
        self.assertNotIn("os.chdir", source)

    def test_core_source_has_no_machine_specific_project_path(self):
        drive_path = re.compile(r"[A-Za-z]:[\\/].*Desktop[\\/]agent", re.IGNORECASE)
        wsl_path = re.compile(r"/mnt/[a-z]/.*Desktop/agent", re.IGNORECASE)
        offenders = []
        paths = [BACKEND / "check_models.py", *PACKAGE.rglob("*.py")]
        for path in paths:
            if any(part in {".venv", "__pycache__"} for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if drive_path.search(text) or wsl_path.search(text):
                offenders.append(str(path.relative_to(BACKEND)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
