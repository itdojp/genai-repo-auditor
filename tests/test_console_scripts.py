from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from genai_repo_auditor import audit_cli, batch_cli, cli  # noqa: E402


def pyproject_scripts(text: str) -> dict[str, str]:
    lines = text.splitlines()
    try:
        start = lines.index("[project.scripts]") + 1
    except ValueError as exc:
        raise AssertionError("pyproject.toml is missing [project.scripts]") from exc
    scripts: dict[str, str] = {}
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("["):
            break
        name, value = stripped.split("=", 1)
        scripts[name.strip()] = value.strip().strip('"')
    return scripts


class ConsoleScriptTests(unittest.TestCase):
    maxDiff = None

    def command_names(self) -> list[str]:
        return [path.name for path in sorted((REPO_ROOT / "bin").glob("gra-*")) if path.is_file()]

    def capture_dispatch(self, command: str, args: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = cli.dispatch(command, args)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_console_script_registry_matches_current_command_surface(self) -> None:
        commands = self.command_names()
        self.assertEqual(35, len(commands))
        self.assertEqual(commands, list(cli.COMMANDS))

        scripts = pyproject_scripts((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        expected = {command: f"genai_repo_auditor.cli:{command.replace('-', '_')}" for command in commands}
        self.assertEqual(expected, scripts)
        for entrypoint in expected.values():
            _, function_name = entrypoint.split(":", 1)
            self.assertTrue(callable(getattr(cli, function_name)))

    def test_packaged_python_dispatch_preserves_help_and_version_contracts(self) -> None:
        expected_version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").splitlines()[0].strip()
        for command in ("gra-agent-check", "gra-doctor", "gra-validate-report", "gra-audit", "gra-batch"):
            with self.subTest(command=command):
                status, stdout, stderr = self.capture_dispatch(command, ["--version"])
                self.assertEqual(0, status, stderr)
                self.assertEqual(f"{command} {expected_version}\n", stdout)
                self.assertEqual("", stderr)

                status, stdout, stderr = self.capture_dispatch(command, ["--help"])
                self.assertEqual(0, status, stderr)
                self.assertIn(command, stdout)
                self.assertIn("usage", stdout.lower())
                self.assertEqual("", stderr)


    def write_minimal_resource_root(self, root: Path) -> None:
        (root / "prompts").mkdir(parents=True, exist_ok=True)
        (root / "prompts" / "AGENTS.audit.md").write_text("fake prompt", encoding="utf-8")
        (root / "templates" / "reports").mkdir(parents=True, exist_ok=True)
        (root / "templates" / "reports" / "findings.schema.json").write_text("{}", encoding="utf-8")
        (root / "templates" / "taxonomies").mkdir(parents=True, exist_ok=True)
        (root / "templates" / "taxonomies" / "owasp-llm-2025.json").write_text("{}", encoding="utf-8")
        (root / "templates" / "agent-workers").mkdir(parents=True, exist_ok=True)
        (root / "templates" / "agent-workers" / "codex-cli.json").write_text("{}", encoding="utf-8")

    def test_console_dispatch_does_not_execute_code_from_resource_override(self) -> None:
        tmp_parent = REPO_ROOT / ".test-tmp"
        tmp_parent.mkdir(exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=tmp_parent))
        original = os.environ.get("GENAI_REPO_AUDITOR_RESOURCE_ROOT")
        try:
            fake_root = work_dir / "fake-root"
            self.write_minimal_resource_root(fake_root)
            (fake_root / "bin").mkdir()
            (fake_root / "bin" / "gra-agent-check").write_text(
                "#!/usr/bin/env python3\nraise SystemExit('override bin executed')\n",
                encoding="utf-8",
            )
            os.environ["GENAI_REPO_AUDITOR_RESOURCE_ROOT"] = str(fake_root)
            status, stdout, stderr = self.capture_dispatch("gra-agent-check", ["--version"])
            expected_version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").splitlines()[0].strip()
            self.assertEqual(0, status, stderr)
            self.assertEqual(f"gra-agent-check {expected_version}\n", stdout)
            self.assertEqual("", stderr)
        finally:
            if original is None:
                os.environ.pop("GENAI_REPO_AUDITOR_RESOURCE_ROOT", None)
            else:
                os.environ["GENAI_REPO_AUDITOR_RESOURCE_ROOT"] = original
            shutil.rmtree(work_dir, ignore_errors=True)
            with contextlib.suppress(OSError):
                tmp_parent.rmdir()


    def write_mock_audit_commands(self, mock_bin: Path) -> None:
        mock_bin.mkdir(parents=True, exist_ok=True)
        gh = mock_bin / "gh"
        gh.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ \"${1:-} ${2:-}\" == \"repo clone\" ]]; then mkdir -p \"${4:?}\"; exit 0; fi\n"
            "if [[ \"${1:-} ${2:-}\" == \"repo view\" ]]; then echo PUBLIC; exit 0; fi\n"
            "echo \"unexpected gh invocation: $*\" >&2\n"
            "exit 97\n",
            encoding="utf-8",
        )
        git = mock_bin / "git"
        git.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ \"${1:-}\" == \"-C\" && \"${3:-} ${4:-}\" == \"rev-parse HEAD\" ]]; then echo 0123456789abcdef0123456789abcdef01234567; exit 0; fi\n"
            "if [[ \"${1:-}\" == \"-C\" && \"${3:-} ${4:-}\" == \"branch --show-current\" ]]; then echo main; exit 0; fi\n"
            "echo \"unexpected git invocation: $*\" >&2\n"
            "exit 97\n",
            encoding="utf-8",
        )
        codex = mock_bin / "codex"
        codex.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "echo \"codex mock should not be executed in prepare or goal mode\" >&2\n"
            "exit 97\n",
            encoding="utf-8",
        )
        for path in (gh, git, codex):
            path.chmod(0o755)

    def test_audit_lock_failure_does_not_remove_existing_live_lock(self) -> None:
        tmp_parent = REPO_ROOT / ".test-tmp"
        tmp_parent.mkdir(exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=tmp_parent))
        old_path = os.environ.get("PATH", "")
        try:
            mock_bin = work_dir / "mock-bin"
            self.write_mock_audit_commands(mock_bin)
            os.environ["PATH"] = f"{mock_bin}{os.pathsep}{old_path}"
            runs_dir = work_dir / "runs"
            existing_lock = runs_dir / ".locks" / "acme__api.lockdir"
            existing_lock.mkdir(parents=True)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = audit_cli.main(
                    [
                        "--repo",
                        "acme/api",
                        "--mode",
                        "prepare",
                        "--runs-dir",
                        str(runs_dir),
                        "--run-id",
                        "second",
                    ],
                    prog="gra-audit",
                )
            self.assertEqual(12, status)
            self.assertIn("Another audit appears to be running", stderr.getvalue())
            self.assertTrue(existing_lock.is_dir(), "failed lock acquisition removed another process lock")
        finally:
            os.environ["PATH"] = old_path
            shutil.rmtree(work_dir, ignore_errors=True)
            with contextlib.suppress(OSError):
                tmp_parent.rmdir()

    def test_batch_child_audit_ignores_cwd_package_shadowing(self) -> None:
        tmp_parent = REPO_ROOT / ".test-tmp"
        tmp_parent.mkdir(exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=tmp_parent))
        old_path = os.environ.get("PATH", "")
        old_cwd = Path.cwd()
        try:
            mock_bin = work_dir / "mock-bin"
            self.write_mock_audit_commands(mock_bin)
            fake_package = work_dir / "shadow" / "genai_repo_auditor"
            fake_package.mkdir(parents=True)
            (fake_package / "__init__.py").write_text("", encoding="utf-8")
            (fake_package / "audit_cli.py").write_text(
                "print('FAKE_AUDIT_CLI_EXECUTED')\nraise SystemExit(0)\n",
                encoding="utf-8",
            )
            os.environ["PATH"] = f"{mock_bin}{os.pathsep}{old_path}"
            os.chdir(fake_package.parent)
            status = batch_cli.run_one(
                "acme/api",
                log_dir=work_dir / "logs",
                runs_dir=work_dir / "runs",
                mode="goal",
                model="gpt-test",
                effort="low",
                depth="1",
                extra_args=[],
            )
            self.assertEqual(0, status)
            log = (work_dir / "logs" / "acme__api.log").read_text(encoding="utf-8")
            self.assertNotIn("FAKE_AUDIT_CLI_EXECUTED", log)
            self.assertIn("Prepared interactive /goal run", log)
            self.assertTrue((work_dir / "runs" / "acme__api").is_dir())
        finally:
            os.chdir(old_cwd)
            os.environ["PATH"] = old_path
            shutil.rmtree(work_dir, ignore_errors=True)
            with contextlib.suppress(OSError):
                tmp_parent.rmdir()

    def test_audit_and_batch_console_adapters_validate_arguments_without_external_tools(self) -> None:
        old_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = ""
            status, stdout, stderr = self.capture_dispatch("gra-audit", [])
            self.assertEqual(2, status)
            self.assertEqual("", stdout)
            self.assertIn("--repo is required", stderr)
            self.assertIn("usage", stderr.lower())

            status, stdout, stderr = self.capture_dispatch("gra-batch", [])
            self.assertEqual(2, status)
            self.assertEqual("", stdout)
            self.assertIn("--repo-list FILE is required", stderr)
            self.assertIn("usage", stderr.lower())
        finally:
            os.environ["PATH"] = old_path


if __name__ == "__main__":
    unittest.main(verbosity=2)
