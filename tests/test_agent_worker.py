from __future__ import annotations

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
sys.path.insert(0, str(REPO_ROOT / "lib"))

from agent_worker import (  # noqa: E402
    CODEX_PROFILE_ID,
    AgentWorkerProfileError,
    check_profile_executable,
    codex_worker_executable,
    load_profile,
    load_profiles,
    validate_profile,
)


class AgentWorkerProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (REPO_ROOT / ".test-tmp").mkdir(exist_ok=True)

    def test_repository_profiles_are_valid_and_include_examples(self) -> None:
        profiles = load_profiles(REPO_ROOT)
        by_id = {profile.id: profile for profile in profiles}

        self.assertEqual({"claude-code", "codex-cli", "generic-cli"}, set(by_id))
        codex = by_id[CODEX_PROFILE_ID]
        self.assertEqual("builtin", codex.profile_status)
        self.assertEqual("codex", codex.executable)
        self.assertTrue(codex.supports_exec)
        self.assertTrue(codex.supports_goal)
        self.assertTrue(codex.supports_json_events)
        self.assertIn("workspace-write", codex.sandbox_modes)
        self.assertFalse(codex.network_default)
        self.assertIn("exec", codex.command_templates)
        self.assertIn("goal", codex.command_templates)

        self.assertEqual("experimental", by_id["claude-code"].profile_status)
        self.assertEqual("experimental", by_id["generic-cli"].profile_status)

    def test_codex_worker_executable_comes_from_builtin_profile(self) -> None:
        self.assertEqual("codex", codex_worker_executable(REPO_ROOT))

    def test_validate_profile_rejects_missing_required_field(self) -> None:
        invalid = {
            "id": "missing-executable",
            "display_name": "Missing executable",
            "profile_status": "experimental",
            "supports_exec": True,
            "supports_goal": False,
            "supports_json_events": False,
            "default_model": "operator-selected",
            "default_effort": "operator-selected",
            "sandbox_modes": ["operator-managed"],
            "network_default": False,
            "command_templates": {"exec": "agent --input -"},
        }
        with self.assertRaisesRegex(AgentWorkerProfileError, "missing required fields: executable"):
            validate_profile(invalid)

    def test_validate_profile_requires_exec_template_when_supports_exec(self) -> None:
        invalid = {
            "id": "bad-template",
            "display_name": "Bad template",
            "profile_status": "experimental",
            "executable": "agent",
            "supports_exec": True,
            "supports_goal": False,
            "supports_json_events": False,
            "default_model": "operator-selected",
            "default_effort": "operator-selected",
            "sandbox_modes": ["operator-managed"],
            "network_default": False,
            "command_templates": {"other": "agent"},
        }
        with self.assertRaisesRegex(AgentWorkerProfileError, "supports_exec requires command_templates.exec"):
            validate_profile(invalid)

    def test_check_profile_executable_reports_available_without_running_command(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".test-tmp") as temp_dir:
            root = Path(temp_dir)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            executable = fake_bin / "codex"
            sentinel = root / "invoked.txt"
            executable.write_text(f"#!/bin/sh\necho invoked > {sentinel}\nexit 97\n", encoding="utf-8")
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            profile = load_profile(REPO_ROOT, CODEX_PROFILE_ID)
            check = check_profile_executable(profile, path_env=str(fake_bin))

            self.assertTrue(check["available"])
            self.assertEqual(str(executable), check["resolved_path"])
            self.assertFalse(sentinel.exists(), "profile check must not execute the worker CLI")

    def test_check_profile_executable_reports_missing(self) -> None:
        profile = load_profile(REPO_ROOT, CODEX_PROFILE_ID)
        check = check_profile_executable(profile, path_env=os.devnull)

        self.assertFalse(check["available"])
        self.assertIsNone(check["resolved_path"])
        self.assertIn("was not found on PATH", "\n".join(check["diagnostics"]))

    def test_gra_agent_check_lists_profiles(self) -> None:
        cp = subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "gra-agent-check"), "--list"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        self.assertEqual(0, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertIn("codex-cli", cp.stdout)
        self.assertIn("claude-code", cp.stdout)
        self.assertIn("generic-cli", cp.stdout)
        self.assertIn("experimental", cp.stdout)

    def test_gra_agent_check_missing_executable_is_clear_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".test-tmp") as temp_dir:
            profiles_dir = Path(temp_dir) / "profiles"
            profiles_dir.mkdir()
            (profiles_dir / "missing-agent.json").write_text(
                json.dumps(
                    {
                        "id": "missing-agent",
                        "display_name": "Missing agent",
                        "profile_status": "experimental",
                        "executable": "missing-agent-binary",
                        "supports_exec": True,
                        "supports_goal": False,
                        "supports_json_events": False,
                        "default_model": "operator-selected",
                        "default_effort": "operator-selected",
                        "sandbox_modes": ["operator-managed"],
                        "network_default": False,
                        "command_templates": {"exec": "missing-agent-binary --input -"},
                    }
                ),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PATH"] = str(Path(temp_dir) / "empty-bin")
            cp = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "bin" / "gra-agent-check"),
                    "--profiles-dir",
                    str(profiles_dir),
                    "--profile",
                    "missing-agent",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
            )

        self.assertEqual(1, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        combined = cp.stdout + cp.stderr
        self.assertIn("missing-agent-binary", combined)
        self.assertIn("was not found on PATH", combined)

    def test_gra_agent_check_codex_profile_reports_missing_codex(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".test-tmp") as temp_dir:
            empty_bin = Path(temp_dir) / "empty-bin"
            empty_bin.mkdir()
            env = os.environ.copy()
            env["PATH"] = str(empty_bin)
            cp = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "bin" / "gra-agent-check"),
                    "--profile",
                    "codex-cli",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
            )

        self.assertEqual(1, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        combined = cp.stdout + cp.stderr
        self.assertIn("codex", combined)
        self.assertIn("was not found on PATH", combined)


if __name__ == "__main__":
    (REPO_ROOT / ".test-tmp").mkdir(exist_ok=True)
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(REPO_ROOT / ".test-tmp", ignore_errors=True)
