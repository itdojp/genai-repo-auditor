from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from gralib import build_codex_exec_args, codex_config_arg  # noqa: E402


class CodexExecArgsTests(unittest.TestCase):
    def test_build_codex_exec_args_uses_exec_compatible_approval_config(self) -> None:
        args = build_codex_exec_args(
            run_dir=Path("/workspace/run"),
            model="gpt-fixture",
            effort="medium",
            network=False,
            output_last=Path("/workspace/run/codex-final.md"),
        )

        self.assertEqual(["codex", "exec"], args[:2])
        self.assertNotIn("--ask-for-approval", args)
        self.assertFalse(any(arg.startswith("--ask-for-approval=") for arg in args))
        self.assertIn("--sandbox", args)
        self.assertIn("workspace-write", args)
        self.assertIn("--output-last-message", args)
        self.assertIn("--json", args)
        self.assertEqual("-", args[-1])
        self.assertIn('approval_policy="never"', args)
        self.assertIn('model_reasoning_effort="medium"', args)
        self.assertIn('web_search="disabled"', args)
        self.assertIn("sandbox_workspace_write.network_access=false", args)

    def test_build_codex_exec_args_preserves_network_and_approval_overrides(self) -> None:
        args = build_codex_exec_args(
            run_dir=Path("/workspace/run"),
            model="gpt-fixture",
            effort="xhigh",
            network=True,
            output_last=Path("/workspace/run/codex-final.md"),
            approval="on-request",
        )

        self.assertIn('approval_policy="on-request"', args)
        self.assertIn("sandbox_workspace_write.network_access=true", args)

    def test_build_codex_exec_args_supports_read_only_worker_sandbox(self) -> None:
        args = build_codex_exec_args(
            run_dir=Path("run"),
            model="fixture-model",
            effort="medium",
            output_last=Path("last.txt"),
            sandbox="read-only",
            ephemeral=True,
            ignore_user_config=True,
            ignore_rules=True,
            output_schema=Path("response-schema.json"),
        )

        self.assertEqual("read-only", args[args.index("--sandbox") + 1])
        self.assertIn("sandbox_workspace_write.network_access=false", args)
        self.assertIn("--ephemeral", args)
        self.assertIn("--ignore-user-config", args)
        self.assertIn("--ignore-rules", args)
        self.assertEqual("response-schema.json", args[args.index("--output-schema") + 1])
        with self.assertRaisesRegex(ValueError, "unsupported Codex sandbox"):
            build_codex_exec_args(
                run_dir=Path("run"),
                model="fixture-model",
                effort="medium",
                output_last=Path("last.txt"),
                sandbox="danger-full-access",
            )
        self.assertNotIn("--ask-for-approval", args)

    def test_codex_config_arg_renders_toml_safe_string_values(self) -> None:
        self.assertEqual('approval_policy="never"', codex_config_arg("approval_policy", "never"))
        self.assertEqual(
            'model_reasoning_effort="x\\\"high"',
            codex_config_arg("model_reasoning_effort", 'x"high'),
        )
        self.assertEqual("sandbox_workspace_write.network_access=false", codex_config_arg("sandbox_workspace_write.network_access", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
