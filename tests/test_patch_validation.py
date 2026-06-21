from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from patch_validation import PatchValidationError, parse_operator_command


class PatchValidationTests(unittest.TestCase):
    def test_parse_operator_command_rejects_url_argument(self) -> None:
        with self.assertRaisesRegex(PatchValidationError, "network-capable arguments"):
            parse_operator_command("python3 -c \"print('https://example.invalid')\"")

    def test_parse_operator_command_rejects_dynamic_import_network_argument(self) -> None:
        with self.assertRaisesRegex(PatchValidationError, "network-capable arguments"):
            parse_operator_command('python3 -c "__import__(\'urllib.request\')"')

    def test_parse_operator_command_rejects_direct_network_import_argument(self) -> None:
        with self.assertRaisesRegex(PatchValidationError, "network-capable arguments"):
            parse_operator_command('python3 -c "import urllib.request"')

    def test_parse_operator_command_allows_py_compile(self) -> None:
        self.assertEqual(
            ["python3", "-m", "py_compile", "repo/app.py"],
            parse_operator_command("python3 -m py_compile repo/app.py"),
        )


if __name__ == "__main__":
    unittest.main()
