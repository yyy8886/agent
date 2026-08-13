"""Platform selection tests for the Agent command tool."""

import unittest
from unittest.mock import patch

from my_agent_next.app.tools import bash


class NativeShellTests(unittest.TestCase):
    @patch("my_agent_next.app.tools.bash.subprocess.run")
    @patch("my_agent_next.app.tools.bash.os.name", "nt")
    def test_windows_uses_powershell_and_never_bash(self, run):
        run.return_value.stdout = "Windows\n"
        run.return_value.stderr = ""
        run.return_value.returncode = 0

        result = bash.run_bash.invoke({"command": "$env:OS"})

        argv = run.call_args.args[0]
        self.assertEqual(argv[0], "powershell.exe")
        self.assertNotIn("bash", " ".join(argv).lower())
        child_env = run.call_args.kwargs["env"]
        self.assertTrue(child_env["PATH"].startswith(bash.os.path.dirname(bash.sys.executable)))
        self.assertEqual(result, "Windows")

    @patch("my_agent_next.app.tools.bash.subprocess.run")
    @patch("my_agent_next.app.tools.bash.os.name", "posix")
    @patch("my_agent_next.app.tools.bash.os.path.isfile", return_value=True)
    def test_linux_uses_system_bash(self, _isfile, run):
        run.return_value.stdout = "Linux\n"
        run.return_value.stderr = ""
        run.return_value.returncode = 0

        result = bash.run_bash.invoke({"command": "uname -s"})

        self.assertEqual(run.call_args.args[0], ["/bin/bash", "-lc", "uname -s"])
        self.assertEqual(result, "Linux")


if __name__ == "__main__":
    unittest.main()
