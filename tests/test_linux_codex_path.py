"""Linux desktop PATH can omit the user's npm installation."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codex_pet.codex_client import CodexClient


class LinuxCodexPathTest(unittest.TestCase):
    def test_npm_global_outside_path(self):
        with tempfile.TemporaryDirectory() as home:
            codex = Path(home) / ".npm-global/bin/codex"
            codex.parent.mkdir(parents=True)
            codex.touch(mode=0o755)
            with patch.dict(os.environ, {"HOME": home, "PATH": "/usr/bin:/bin"}), \
                    patch("codex_pet.codex_client.sys.platform", "linux"), \
                    patch("codex_pet.codex_client.shutil.which", return_value=None):
                self.assertEqual(CodexClient._locate_codex(), (str(codex), []))


if __name__ == "__main__":
    unittest.main()
