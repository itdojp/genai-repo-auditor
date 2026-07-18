from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCTOR = REPO_ROOT / "bin" / "gra-doctor"


class DoctorTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def write_mock_command(self, name: str, body: str) -> Path:
        mock_bin = self.work_dir / "bin"
        mock_bin.mkdir(exist_ok=True)
        path = mock_bin / name
        path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def doctor_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = str(self.work_dir / "bin")
        env["GITHUB_TOKEN"] = "super-secret-token-value"
        env["PASSWORD"] = "super-secret-password-value"
        return env

    def run_doctor(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(DOCTOR), *args],
            cwd=REPO_ROOT,
            env=env or self.doctor_env(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )

    def test_gra_doctor_json_reports_readiness_without_running_worker_or_leaking_secrets(self) -> None:
        sentinel = self.work_dir / "codex-invoked.txt"
        self.write_mock_command("git", 'if [ "${1:-}" = "--version" ]; then echo "git version 9.9.9"; exit 0; fi\nexit 97\n')
        self.write_mock_command(
            "gh",
            'if [ "${1:-}" = "--version" ]; then echo "gh version 9.9.9"; exit 0; fi\n'
            'if [ "${1:-} ${2:-} ${3:-}" = "auth status --hostname" ]; then exit 0; fi\n'
            'exit 97\n',
        )
        self.write_mock_command("codex", f'echo invoked > "{sentinel}"\nexit 97\n')

        cp = self.run_doctor("--json", "--probe-external-tools", "--runs-dir", str(self.work_dir / "runs"))
        self.assertEqual(0, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertEqual("", cp.stderr)
        self.assertNotIn("super-secret", cp.stdout)
        self.assertFalse(sentinel.exists(), "gra-doctor must not execute the worker CLI")

        data = json.loads(cp.stdout)
        self.assertEqual("1", data["schema_version"])
        self.assertEqual("genai-repo-auditor", data["tool"])
        self.assertIn(data["overall_status"], {"ok", "warning"})
        self.assertEqual("ok", data["checks"]["python"]["status"])
        self.assertEqual("ok", data["checks"]["git"]["status"])
        self.assertTrue(data["checks"]["git"]["version_checked"])
        self.assertEqual("ok", data["checks"]["gh"]["status"])
        self.assertTrue(data["checks"]["gh"]["version_checked"])
        self.assertTrue(data["checks"]["gh_auth"]["authenticated"])
        self.assertTrue(data["checks"]["gh_auth"]["checked"])
        self.assertEqual(["GITHUB_TOKEN"], data["checks"]["github_token_environment"]["present_names"])
        self.assertEqual("GITHUB_TOKEN", data["checks"]["github_token_environment"]["effective_name"])
        self.assertFalse(data["checks"]["github_token_environment"]["values_exposed"])
        self.assertTrue(data["checks"]["worker"]["available"])
        self.assertTrue(data["checks"]["run_directory"]["writable"])
        self.assertEqual("ok", data["checks"]["packaged_resources"]["status"])

    def test_gra_doctor_default_does_not_execute_external_git_or_gh(self) -> None:
        sentinel = self.work_dir / "external-invoked.txt"
        self.write_mock_command("git", f'echo git "$@" >> "{sentinel}"\nexit 97\n')
        self.write_mock_command("gh", f'echo gh "$@" >> "{sentinel}"\nexit 97\n')

        cp = self.run_doctor("--json", "--runs-dir", str(self.work_dir / "runs"))
        self.assertEqual(0, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertFalse(sentinel.exists(), "default gra-doctor must not execute git or gh")
        data = json.loads(cp.stdout)
        self.assertFalse(data["external_tool_probes_enabled"])
        self.assertEqual("ok", data["checks"]["git"]["status"])
        self.assertFalse(data["checks"]["git"]["version_checked"])
        self.assertEqual("ok", data["checks"]["gh"]["status"])
        self.assertFalse(data["checks"]["gh"]["version_checked"])
        self.assertIsNone(data["checks"]["gh_auth"]["authenticated"])
        self.assertFalse(data["checks"]["gh_auth"]["checked"])
        self.assertIn(data["checks"]["platform_support"]["environment"], {"linux", "wsl2", "macos", "native-windows"})

    def test_gra_doctor_reports_github_token_name_precedence_without_values(self) -> None:
        self.write_mock_command("git", "exit 0\n")
        self.write_mock_command("gh", "exit 0\n")
        self.write_mock_command("codex", "exit 0\n")
        env = self.doctor_env()
        env["GH_TOKEN"] = "ghp_primary-secret-value"
        env["GITHUB_TOKEN"] = "ghp_secondary-secret-value"

        cp = self.run_doctor("--json", "--runs-dir", str(self.work_dir / "runs"), env=env)

        self.assertEqual(0, cp.returncode, cp.stderr)
        self.assertNotIn("primary-secret", cp.stdout)
        self.assertNotIn("secondary-secret", cp.stdout)
        data = json.loads(cp.stdout)
        check = data["checks"]["github_token_environment"]
        self.assertEqual(["GH_TOKEN", "GITHUB_TOKEN"], check["present_names"])
        self.assertEqual("GH_TOKEN", check["effective_name"])
        self.assertFalse(check["values_exposed"])
        self.assertTrue(any("stored gh credentials" in item for item in check["diagnostics"]))

    def test_gra_doctor_external_probe_redacts_command_output_and_strips_secret_env(self) -> None:
        self.write_mock_command(
            "git",
            'if [ "${1:-}" = "--version" ]; then echo "git ${GITHUB_TOKEN:-missing}"; exit 0; fi\nexit 97\n',
        )
        self.write_mock_command(
            "gh",
            'if [ "${1:-}" = "--version" ]; then echo "gh $HOME/local-secret-token-bin/gh"; exit 0; fi\n'
            'if [ "${1:-} ${2:-} ${3:-}" = "auth status --hostname" ]; then exit 0; fi\n'
            'exit 97\n',
        )

        cp = self.run_doctor("--json", "--probe-external-tools", "--runs-dir", str(self.work_dir / "runs"))
        self.assertEqual(0, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertNotIn("super-secret-token-value", cp.stdout)
        self.assertNotIn("local-secret-token-bin", cp.stdout)
        data = json.loads(cp.stdout)
        self.assertEqual("git missing", data["checks"]["git"]["version"])
        self.assertIn("<redacted>", data["checks"]["gh"]["version"])

    def test_gra_doctor_redacts_worker_paths_in_structured_diagnostics(self) -> None:
        secret_bin = self.work_dir / "local-secret-token-bin"
        secret_bin.mkdir()
        codex = secret_bin / "codex"
        codex.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
        codex.chmod(codex.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        env = os.environ.copy()
        env["PATH"] = str(secret_bin)

        cp = self.run_doctor("--json", "--runs-dir", str(self.work_dir / "runs"), env=env)
        self.assertEqual(0, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertNotIn("local-secret-token-bin", cp.stdout)
        self.assertIn("<redacted>", cp.stdout)
        data = json.loads(cp.stdout)
        self.assertEqual("ok", data["checks"]["worker"]["status"])
        self.assertIn("<redacted>", data["checks"]["worker"]["resolved_path"])
        self.assertTrue(
            any("<redacted>" in diagnostic for diagnostic in data["checks"]["worker"]["diagnostics"]),
            data["checks"]["worker"]["diagnostics"],
        )

    def test_gra_doctor_reports_missing_tools_as_safe_warnings_by_default(self) -> None:
        env = os.environ.copy()
        env["PATH"] = str(self.work_dir / "empty-bin")
        env["GITHUB_TOKEN"] = "super-secret-token-value"
        cp = self.run_doctor("--json", "--runs-dir", str(self.work_dir / "runs"), env=env)
        self.assertEqual(0, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertNotIn("super-secret", cp.stdout + cp.stderr)
        data = json.loads(cp.stdout)
        self.assertEqual("error", data["checks"]["git"]["status"])
        self.assertEqual("error", data["checks"]["gh"]["status"])
        self.assertEqual("warning", data["checks"]["worker"]["status"])
        self.assertEqual("error", data["overall_status"])

    def test_gra_doctor_strict_exits_nonzero_on_required_errors(self) -> None:
        env = os.environ.copy()
        env["PATH"] = str(self.work_dir / "empty-bin")
        cp = self.run_doctor("--json", "--strict", "--runs-dir", str(self.work_dir / "runs"), env=env)
        self.assertEqual(1, cp.returncode)
        data = json.loads(cp.stdout)
        self.assertEqual("error", data["overall_status"])

    def test_scanner_readiness_requires_explicit_scanner_runtime_probe_opt_in(self) -> None:
        cp = self.run_doctor(
            "--json",
            "--probe-external-tools",
            "--scanner-run",
            str(self.work_dir / "run"),
            "--scanner-tool",
            "gitleaks",
        )
        self.assertEqual(2, cp.returncode)
        self.assertIn("requires --probe-scanner-runtime", cp.stderr)

    def test_scanner_runtime_probe_requires_scanner_pair(self) -> None:
        cp = self.run_doctor("--json", "--probe-scanner-runtime")
        self.assertEqual(2, cp.returncode)
        self.assertIn("requires --scanner-run and --scanner-tool", cp.stderr)

    def test_scanner_readiness_rejects_generic_external_probes(self) -> None:
        cp = self.run_doctor(
            "--json",
            "--probe-scanner-runtime",
            "--probe-external-tools",
            "--scanner-run",
            str(self.work_dir / "run"),
            "--scanner-tool",
            "gitleaks",
        )
        self.assertEqual(2, cp.returncode)
        self.assertIn("cannot be combined with --probe-external-tools", cp.stderr)

    def test_scanner_readiness_usage_errors_do_not_echo_invalid_values(self) -> None:
        secret_like_value = "private-user-name-token"
        for option in ("--scanner-tool", "--scanner-sandbox-profile"):
            cp = self.run_doctor(
                "--json",
                "--probe-scanner-runtime",
                "--scanner-run",
                str(self.work_dir / "run"),
                "--scanner-tool",
                "gitleaks" if option != "--scanner-tool" else secret_like_value,
                *([option, secret_like_value] if option != "--scanner-tool" else []),
            )
            with self.subTest(option=option):
                self.assertEqual(2, cp.returncode)
                self.assertNotIn(secret_like_value, cp.stderr)

    def test_scanner_readiness_reuses_bounded_contract_without_scanner_execution(self) -> None:
        run_dir = self.work_dir / "run"
        (run_dir / "repo").mkdir(parents=True)
        (run_dir / "reports").mkdir()
        (run_dir / "context.json").write_text(
            json.dumps(
                {
                    "run_id": "doctor-scanner-readiness",
                    "repo": "example/doctor-readiness",
                    "target_repo_dir": "repo",
                    "reports_dir": "reports",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        unexpected_command_log = self.work_dir / "unexpected-commands.log"
        for command in ("git", "gh", "codex", "runsc"):
            self.write_mock_command(
                command,
                f'printf \'{command} %s\\n\' "$*" >> "{unexpected_command_log}"\nexit 97\n',
            )
        command_log = self.work_dir / "docker-commands.log"
        self.write_mock_command(
            "docker",
            f'printf \'%s\\n\' "$*" >> "{command_log}"\n'
            'case "$*" in\n'
            "  *' version') exit 0 ;;\n"
            "  *' image inspect '*) exit 0 ;;\n"
            "  *) exit 97 ;;\n"
            "esac\n",
        )
        env = os.environ.copy()
        env["PATH"] = str(self.work_dir / "bin")
        credential_markers = (
            "ACCESS_KEY",
            "API_KEY",
            "AUTH_CONFIG",
            "AUTH_FILE",
            "CREDENTIAL",
            "PASSWORD",
            "PASSWD",
            "PRIVATE_KEY",
            "SECRET",
            "SESSION_TOKEN",
            "TOKEN",
        )
        for name in list(env):
            if any(marker in name.upper() for marker in credential_markers):
                env.pop(name)

        cp = self.run_doctor(
            "--json",
            "--probe-scanner-runtime",
            "--runs-dir",
            str(self.work_dir / "runs"),
            "--scanner-run",
            str(run_dir),
            "--scanner-tool",
            "syft",
            env=env,
        )
        self.assertEqual(0, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        data = json.loads(cp.stdout)
        self.assertFalse(data["external_tool_probes_enabled"])
        self.assertTrue(data["scanner_runtime_probes_enabled"])
        self.assertFalse(unexpected_command_log.exists(), "scanner-only doctor must not execute git, gh, codex, or runsc")
        check = data["checks"]["scanner_execution_readiness"]
        self.assertTrue(check["checked"])
        self.assertIn(check["state"], {"ready", "experimental"})
        self.assertEqual(["ready"], check["reason_codes"])
        self.assertFalse(check["readiness"]["scanner_executed"])
        self.assertFalse(check["readiness"]["probes"]["image_pulled"])
        commands = command_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(2, len(commands), commands)
        self.assertFalse(any(" run " in f" {item} " or " pull " in f" {item} " for item in commands))


if __name__ == "__main__":
    unittest.main(verbosity=2)
