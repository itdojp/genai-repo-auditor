from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from gralib import env_from_context  # noqa: E402
from template_env import (  # noqa: E402
    build_template_values,
    controlled_placeholder_from_env_key,
    is_denied_placeholder,
    validate_template_env_key,
)


class TemplateEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def render_env(self, **overrides: str) -> dict[str, str]:
        env = {key: value for key, value in os.environ.items() if not key.startswith("GRA_TEMPLATE_")}
        env.update(overrides)
        return env

    def run_render_template(self, template: Path, out: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, REPO_ROOT / "lib" / "render_template.py", template, out],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
            timeout=20,
        )

    def test_build_template_values_uses_allowlist_and_controlled_prefix(self) -> None:
        values = build_template_values(
            {
                "RUN_ID": "run-123",
                "REPO": "OWNER/REPO",
                "PATH": "/usr/bin",
                "OPENAI_API_KEY": "should-not-appear",
                "GRA_TEMPLATE_CUSTOM_VALUE": "controlled",
            }
        )
        self.assertEqual(values["RUN_ID"], "run-123")
        self.assertEqual(values["REPO"], "OWNER/REPO")
        self.assertEqual(values["CUSTOM_VALUE"], "controlled")
        self.assertNotIn("PATH", values)
        self.assertNotIn("OPENAI_API_KEY", values)

    def test_template_key_validation_denies_invalid_or_secret_like_keys(self) -> None:
        validate_template_env_key("TARGET_ID")
        self.assertFalse(is_denied_placeholder("TARGET_ID"))
        for key in ["target_id", "TARGET-ID", "API_KEY", "SESSION_TOKEN", "PASSWORD"]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    validate_template_env_key(key)
        with self.assertRaisesRegex(ValueError, "denied controlled template placeholder"):
            controlled_placeholder_from_env_key("GRA_TEMPLATE_API_KEY")
        with self.assertRaisesRegex(ValueError, "invalid controlled template placeholder"):
            controlled_placeholder_from_env_key("GRA_TEMPLATE_")

    def test_render_template_replaces_known_values_and_rejects_unknown_or_denied_placeholders(self) -> None:
        template = self.work_dir / "template.md"
        out = self.work_dir / "out.md"
        env = self.render_env(RUN_ID="run-1", REPO="OWNER/REPO", GRA_TEMPLATE_CUSTOM_VALUE="controlled")

        template.write_text("run={{RUN_ID}}\nrepo={{REPO}}\ncustom={{CUSTOM_VALUE}}\n", encoding="utf-8")
        cp = self.run_render_template(template, out, env)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(out.read_text(encoding="utf-8"), "run=run-1\nrepo=OWNER/REPO\ncustom=controlled\n")

        out.unlink()
        template.write_text("unknown={{UNKNOWN_PLACEHOLDER}}\n", encoding="utf-8")
        cp_unknown = self.run_render_template(template, out, env)
        self.assertEqual(cp_unknown.returncode, 2)
        self.assertIn("unknown template placeholder: UNKNOWN_PLACEHOLDER", cp_unknown.stderr)
        self.assertFalse(out.exists())

        template.write_text("secret={{OPENAI_API_KEY}}\n", encoding="utf-8")
        cp_denied = self.run_render_template(template, out, env)
        self.assertEqual(cp_denied.returncode, 2)
        self.assertIn("denied template placeholder: OPENAI_API_KEY", cp_denied.stderr)
        self.assertFalse(out.exists())

    def test_env_from_context_is_minimal_and_rejects_secret_like_extra_keys(self) -> None:
        run_dir = self.work_dir / "run"
        run_dir.mkdir()
        (run_dir / "context.json").write_text(
            json.dumps(
                {
                    "run_id": "fixture-run",
                    "repo": "OWNER/REPO",
                    "repo_slug": "OWNER__REPO",
                    "branch": "main",
                    "commit": "abc123",
                    "visibility": "PRIVATE",
                    "reports_dir": "reports",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "fixture-secret"
        try:
            env = env_from_context(run_dir, {"TARGET_ID": "TGT-001"})
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original

        self.assertEqual(env["RUN_ID"], "fixture-run")
        self.assertEqual(env["REPO"], "OWNER/REPO")
        self.assertEqual(env["TARGET_ID"], "TGT-001")
        self.assertNotIn("PATH", env)
        self.assertNotIn("OPENAI_API_KEY", env)
        with self.assertRaisesRegex(ValueError, "denied template environment key: API_KEY"):
            env_from_context(run_dir, {"API_KEY": "fixture-secret"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
