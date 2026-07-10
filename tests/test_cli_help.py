from __future__ import annotations

import contextlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "bin"
BASH = shutil.which("bash") or "/bin/bash"


class CliHelpTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))
        self.mock_bin = self.work_dir / "bin"
        self.mock_bin.mkdir()
        self.sentinel = self.work_dir / "external-command-invocations.txt"
        self._write_forbidden_command("gh")
        self._write_forbidden_command("codex")
        self.env = os.environ.copy()
        self.env.update(
            {
                "PATH": f"{self.mock_bin}{os.pathsep}{self.env.get('PATH', '')}",
                "GRA_HELP_SENTINEL": str(self.sentinel),
                "PYTHONUNBUFFERED": "1",
            }
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def _write_forbidden_command(self, name: str) -> None:
        path = self.mock_bin / name
        path.write_text(
            "#!/bin/sh\n"
            "echo \"$0 $*\" >> \"$GRA_HELP_SENTINEL\"\n"
            "exit 97\n",
            encoding="utf-8",
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def command_paths(self) -> list[Path]:
        return sorted(path for path in BIN_DIR.glob("gra-*") if path.is_file())

    def invoke(self, path: Path, args: Iterable[str]) -> subprocess.CompletedProcess[str]:
        first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        if "bash" in first_line:
            cmd = [BASH, str(path), *args]
        elif "python3" in first_line:
            cmd = [sys.executable, str(path), *args]
        else:
            cmd = [str(path), *args]
        return subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )

    def assert_no_traceback_or_shell_error(self, cp: subprocess.CompletedProcess[str]) -> None:
        combined = cp.stdout + cp.stderr
        self.assertNotIn("Traceback (most recent call last)", combined)
        self.assertNotIn("command not found", combined)
        self.assertNotIn("No such file or directory", combined)
        self.assertNotIn("unsupported arguments", combined)

    def test_every_gra_command_exposes_help_without_external_tools(self) -> None:
        commands = self.command_paths()
        self.assertEqual(34, len(commands))
        for path in commands:
            with self.subTest(command=path.name):
                cp = self.invoke(path, ["--help"])
                self.assertEqual(cp.returncode, 0, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
                self.assertEqual(cp.stderr, "")
                self.assertIn(path.name, cp.stdout)
                self.assertIn("usage", cp.stdout.lower())
                self.assert_no_traceback_or_shell_error(cp)
        self.assertFalse(self.sentinel.exists(), "--help invoked a real external dependency path")

    def test_every_gra_command_exposes_version_without_external_tools(self) -> None:
        for forbidden in ("date", "dirname", "basename", "cat", "gh", "codex"):
            self._write_forbidden_command(forbidden)
        expected_version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").splitlines()[0].strip()

        commands = self.command_paths()
        self.assertEqual(34, len(commands))
        for path in commands:
            with self.subTest(command=path.name):
                cp = self.invoke(path, ["--version"])
                self.assertEqual(cp.returncode, 0, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
                self.assertEqual(cp.stderr, "")
                self.assertEqual(cp.stdout, f"{path.name} {expected_version}\n")
                self.assert_no_traceback_or_shell_error(cp)
        self.assertFalse(self.sentinel.exists(), "--version invoked an external dependency path")

    def test_core_missing_argument_failures_are_usage_errors(self) -> None:
        cases = [
            ("gra-audit", [], 2, "--repo is required"),
            ("gra-batch", [], 2, "--repo-list FILE is required"),
            ("gra-dashboard", [], 2, "the following arguments are required: --run"),
            ("gra-issues", [], 2, "the following arguments are required: --run"),
            ("gra-no-findings", [], 2, "the following arguments are required: --run, --rationale"),
            ("gra-remediate", [], 2, "the following arguments are required: --run"),
            ("gra-run-state", [], 2, "the following arguments are required: --run"),
            ("gra-sandbox-check", [], 2, "the following arguments are required: --run, --profile"),
            ("gra-targets", [], 2, "the following arguments are required: --run"),
            ("gra-taxonomy-preflight", [], 2, "one of the arguments --run --findings is required"),
            ("gra-validate-report", [], 2, "one of --run or --findings is required"),
            ("gra-workflow-profile", [], 2, "the following arguments are required: --run, --profile, --rationale"),
        ]
        for command, args, expected_status, expected_message in cases:
            with self.subTest(command=command):
                cp = self.invoke(BIN_DIR / command, args)
                self.assertEqual(cp.returncode, expected_status, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
                self.assertIn(expected_message, cp.stderr)
                self.assertIn("usage", (cp.stdout + cp.stderr).lower())
                self.assert_no_traceback_or_shell_error(cp)
        self.assertFalse(self.sentinel.exists(), "missing-argument validation invoked external dependencies")


if __name__ == "__main__":
    unittest.main(verbosity=2)
