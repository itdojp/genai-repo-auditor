from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from patch_validation import PatchValidationError, diff_scope_status, parse_operator_command


class PatchValidationTests(unittest.TestCase):
    def test_parse_operator_command_rejects_network_call_argument(self) -> None:
        with self.assertRaisesRegex(PatchValidationError, "network-capable arguments"):
            parse_operator_command("python3 -c \"urlopen('https://example.invalid')\"")

    def test_parse_operator_command_rejects_dynamic_import_network_argument(self) -> None:
        with self.assertRaisesRegex(PatchValidationError, "network-capable arguments"):
            parse_operator_command('python3 -c "__import__(\'urllib.request\')"')

    def test_parse_operator_command_rejects_dynamic_import_expression_argument(self) -> None:
        with self.assertRaisesRegex(PatchValidationError, "network-capable arguments"):
            parse_operator_command('python3 -c "__import__(f\'urllib.{name}\')"')

    def test_parse_operator_command_rejects_direct_network_import_argument(self) -> None:
        with self.assertRaisesRegex(PatchValidationError, "network-capable arguments"):
            parse_operator_command('python3 -c "import urllib.request"')

    def test_parse_operator_command_allows_py_compile(self) -> None:
        self.assertEqual(
            ["python3", "-m", "py_compile", "repo/app.py"],
            parse_operator_command("python3 -m py_compile repo/app.py"),
        )

    def test_diff_scope_rejects_vcs_metadata_paths(self) -> None:
        status, checks = diff_scope_status(
            diff_paths={"repo/.git/config"},
            declared_files=["repo/.git/config"],
            target_prefix="repo",
            max_changed_paths=20,
        )
        self.assertEqual("too-broad", status)
        self.assertTrue(any(check["id"] == "diff-vcs-metadata" for check in checks))


if __name__ == "__main__":
    unittest.main()
