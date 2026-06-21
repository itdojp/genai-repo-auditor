from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import suppress
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from sandbox_profiles import (  # noqa: E402
    SandboxProfileError,
    enforce_sandbox_profile,
    evaluate_sandbox_readiness,
    write_readiness_report,
)


class SandboxProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))
        self.run_dir = self.work_dir / "run"
        self.reports_dir = self.run_dir / "reports"
        self.repo_dir = self.run_dir / "repo"
        self.reports_dir.mkdir(parents=True)
        self.repo_dir.mkdir()
        (self.run_dir / "context.json").write_text(
            json.dumps(
                {
                    "run_id": "sandbox-test",
                    "repo": "example/sandbox",
                    "target_repo_dir": "repo",
                    "reports_dir": "reports",
                    "network_allowed": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with suppress(OSError):
            self.tmp_parent.rmdir()

    def test_source_only_succeeds_without_container_runtime(self) -> None:
        report = evaluate_sandbox_readiness(
            run_dir=self.run_dir,
            profile_id="source-only",
            path_env=str(self.work_dir / "empty-bin"),
            env={},
        )

        self.assertEqual("ready", report["status"])
        self.assertEqual("source-only", report["profile"]["id"])
        self.assertFalse(report["profile"]["executes_target_code"])
        self.assertIn("container-runtime", {check["id"] for check in report["checks"]})
        container_check = next(check for check in report["checks"] if check["id"] == "container-runtime")
        self.assertEqual("info", container_check["status"])

    def test_container_profile_fails_closed_when_runtime_missing(self) -> None:
        report = evaluate_sandbox_readiness(
            run_dir=self.run_dir,
            profile_id="container",
            executable_workflow=True,
            path_env=str(self.work_dir / "empty-bin"),
            env={},
        )

        self.assertEqual("blocked", report["status"])
        failures = [check for check in report["checks"] if check["status"] == "fail"]
        self.assertTrue(any(check["id"] == "container-runtime" for check in failures))

    def test_source_only_rejects_executable_workflow(self) -> None:
        with self.assertRaisesRegex(SandboxProfileError, "executable workflow requested with source-only profile"):
            enforce_sandbox_profile(
                run_dir=self.run_dir,
                profile_id="source-only",
                executable_workflow=True,
                path_env=str(self.work_dir / "empty-bin"),
                env={},
            )

    def test_write_readiness_report_outputs_json_and_markdown(self) -> None:
        report = evaluate_sandbox_readiness(run_dir=self.run_dir, profile_id="local-test", path_env=str(self.work_dir / "empty-bin"), env={})
        out_json, out_md = write_readiness_report(self.run_dir, report)

        self.assertEqual(self.reports_dir / "sandbox-readiness.json", out_json)
        self.assertEqual(self.reports_dir / "SANDBOX_READINESS.md", out_md)
        loaded = json.loads(out_json.read_text(encoding="utf-8"))
        self.assertEqual("local-test", loaded["profile"]["id"])
        self.assertIn("# Sandbox Readiness", out_md.read_text(encoding="utf-8"))

    def test_gra_sandbox_check_source_only_cli_writes_reports(self) -> None:
        cp = subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "gra-sandbox-check"), "--run", str(self.run_dir), "--profile", "source-only", "--json"],
            cwd=REPO_ROOT,
            env={"PATH": str(self.work_dir / "empty-bin"), "PYTHONUNBUFFERED": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )

        self.assertEqual(0, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        report = json.loads(cp.stdout)
        self.assertEqual("ready", report["status"])
        self.assertTrue((self.reports_dir / "sandbox-readiness.json").exists())
        self.assertTrue((self.reports_dir / "SANDBOX_READINESS.md").exists())

    def test_gra_sandbox_check_container_missing_returns_one_and_writes_report(self) -> None:
        cp = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "gra-sandbox-check"),
                "--run",
                str(self.run_dir),
                "--profile",
                "container",
                "--executable-workflow",
                "--json",
            ],
            cwd=REPO_ROOT,
            env={"PATH": str(self.work_dir / "empty-bin"), "PYTHONUNBUFFERED": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )

        self.assertEqual(1, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        report = json.loads(cp.stdout)
        self.assertEqual("blocked", report["status"])
        self.assertTrue((self.reports_dir / "sandbox-readiness.json").exists())
        self.assertIn("container profile requires Docker or Podman", cp.stdout)

if __name__ == "__main__":
    unittest.main(verbosity=2)
