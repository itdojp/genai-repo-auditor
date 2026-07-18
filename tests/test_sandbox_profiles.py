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
    detect_visible_credential_env,
    enforce_sandbox_profile,
    evaluate_sandbox_readiness,
    is_credential_environment_name,
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

    def test_credential_name_classifier_is_unbounded_while_report_names_remain_bounded(self) -> None:
        env = {f"SERVICE_{index:03d}_TOKEN": "not-reported" for index in range(80)}
        self.assertTrue(all(is_credential_environment_name(name) for name in env))
        reported = detect_visible_credential_env(env)
        self.assertEqual(64, len(reported))
        self.assertEqual(sorted(reported), reported)

    def init_clean_git_repo(self) -> None:
        subprocess.run(["git", "init"], cwd=self.repo_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def path_with_git_only(self) -> str:
        git = shutil.which("git")
        if not git:
            self.skipTest("git executable is required for sandbox profile tests")
        bin_dir = self.work_dir / "git-only-bin"
        bin_dir.mkdir()
        try:
            (bin_dir / "git").symlink_to(git)
        except OSError:
            shutil.copy2(git, bin_dir / "git")
        return str(bin_dir)

    def write_context(self, **overrides: object) -> None:
        data = json.loads((self.run_dir / "context.json").read_text(encoding="utf-8"))
        data.update(overrides)
        (self.run_dir / "context.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def check_by_id(self, report: dict[str, object], check_id: str) -> dict[str, object]:
        checks = report["checks"]
        self.assertIsInstance(checks, list)
        return next(check for check in checks if isinstance(check, dict) and check["id"] == check_id)

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
        self.init_clean_git_repo()
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
        self.init_clean_git_repo()
        report = evaluate_sandbox_readiness(run_dir=self.run_dir, profile_id="local-test", path_env=str(self.work_dir / "empty-bin"), env={})
        out_json, out_md = write_readiness_report(self.run_dir, report)

        self.assertEqual("ready", report["status"])
        self.assertEqual(self.reports_dir / "sandbox-readiness.json", out_json)
        self.assertEqual(self.reports_dir / "SANDBOX_READINESS.md", out_md)
        loaded = json.loads(out_json.read_text(encoding="utf-8"))
        self.assertEqual("local-test", loaded["profile"]["id"])
        self.assertEqual(".", loaded["run_dir"])
        self.assertNotIn(str(self.run_dir), json.dumps(loaded))
        self.assertIn("# Sandbox Readiness", out_md.read_text(encoding="utf-8"))

    def test_absolute_repo_dir_under_run_dir_is_allowed_for_generated_contexts(self) -> None:
        self.write_context(repo_dir=str(self.repo_dir))

        report = evaluate_sandbox_readiness(
            run_dir=self.run_dir,
            profile_id="source-only",
            path_env=str(self.work_dir / "empty-bin"),
            env={},
        )

        self.assertEqual("ready", report["status"])
        workspace_check = self.check_by_id(report, "workspace-cleanliness")
        self.assertEqual("repo", workspace_check["details"]["repo_dir"])

    def test_repo_dir_must_stay_under_run_dir(self) -> None:
        outside = self.work_dir / "outside-repo"
        outside.mkdir()
        for override in ({"repo_dir": "../outside-repo"}, {"repo_dir": str(outside)}):
            with self.subTest(override=override):
                self.write_context(**override)
                with self.assertRaisesRegex(SandboxProfileError, "repo_dir"):
                    evaluate_sandbox_readiness(
                        run_dir=self.run_dir,
                        profile_id="source-only",
                        path_env=str(self.work_dir / "empty-bin"),
                        env={},
                    )

    def test_missing_run_dir_is_error(self) -> None:
        with self.assertRaisesRegex(SandboxProfileError, "run directory does not exist"):
            evaluate_sandbox_readiness(
                run_dir=self.work_dir / "missing-run",
                profile_id="source-only",
                path_env=str(self.work_dir / "empty-bin"),
                env={},
            )

    def test_executable_profile_fails_when_repo_state_cannot_be_verified(self) -> None:
        report = evaluate_sandbox_readiness(
            run_dir=self.run_dir,
            profile_id="local-test",
            path_env=str(self.work_dir / "empty-bin"),
            env={},
        )

        self.assertEqual("blocked", report["status"])
        workspace_check = self.check_by_id(report, "workspace-cleanliness")
        self.assertEqual("fail", workspace_check["status"])
        self.assertEqual("required", workspace_check["severity"])
        self.assertIn("not a Git worktree", str(workspace_check["message"]))

    def test_executable_profile_blocks_visible_credentials_without_secret_values(self) -> None:
        self.init_clean_git_repo()

        report = evaluate_sandbox_readiness(
            run_dir=self.run_dir,
            profile_id="local-test",
            path_env=str(self.work_dir / "empty-bin"),
            env={"GH_TOKEN": "ghp_secret-value-that-must-not-appear"},
        )

        self.assertEqual("blocked", report["status"])
        credential_check = self.check_by_id(report, "credential-exposure")
        self.assertEqual("fail", credential_check["status"])
        self.assertEqual(["GH_TOKEN"], credential_check["details"]["credential_environment_names"])
        self.assertNotIn("ghp_secret-value-that-must-not-appear", json.dumps(report))

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
        self.init_clean_git_repo()
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
            env={"PATH": self.path_with_git_only(), "PYTHONUNBUFFERED": "1"},
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
