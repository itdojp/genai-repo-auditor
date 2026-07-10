from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from patch_validation import PatchValidationError, diff_scope_status, parse_operator_command, write_python_network_guard


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

    def test_parse_operator_command_rejects_python_guard_bypass_flags(self) -> None:
        for flag in ["-S", "-E", "-I", "-SE"]:
            with self.subTest(flag=flag):
                with self.assertRaisesRegex(PatchValidationError, "disables the injected Python guard"):
                    parse_operator_command(f"python3 {flag} repo/check.py")

    def test_parse_operator_command_allows_script_arguments_named_like_guard_flags(self) -> None:
        self.assertEqual(
            ["python3", "repo/check.py", "-S", "--case", "-I"],
            parse_operator_command("python3 repo/check.py -S --case -I"),
        )
        self.assertEqual(
            ["python3", "-m", "py_compile", "repo/app.py"],
            parse_operator_command("python3 -m py_compile repo/app.py"),
        )

    def test_python_network_guard_uses_whitespace_fallback_for_unparseable_command_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            guard_dir = write_python_network_guard(Path(tmp))
            code = """
import os
try:
    os.system("python3 -S 'unterminated")
except OSError as exc:
    if 'Python guard bypass flags are disabled' in str(exc):
        raise SystemExit(0)
    raise
raise SystemExit(9)
"""
            env = os.environ.copy()
            env["PYTHONPATH"] = str(guard_dir)
            cp = subprocess.run([sys.executable, "-c", code], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)

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
