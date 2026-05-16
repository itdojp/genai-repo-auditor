from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


class WorkflowHardeningTests(unittest.TestCase):
    def test_lint_workflow_uses_explicit_read_only_permissions(self) -> None:
        text = (WORKFLOWS / "lint.yml").read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("    permissions:\n      contents: read", text)

    def test_codeql_workflow_scans_python_and_github_actions(self) -> None:
        text = (WORKFLOWS / "codeql.yml").read_text(encoding="utf-8")
        self.assertIn("permissions: {}", text)
        self.assertIn("security-events: write", text)
        self.assertIn("github/codeql-action/init@v4", text)
        self.assertIn("github/codeql-action/analyze@v4", text)
        self.assertIn("          - python", text)
        self.assertIn("          - actions", text)

    def test_self_validation_workflow_prepares_offline_fixture_run(self) -> None:
        text = (WORKFLOWS / "self-validation.yml").read_text(encoding="utf-8")
        self.assertIn("permissions: {}", text)
        self.assertIn("    permissions:\n      contents: read", text)
        self.assertIn("--repo fixture/self-validation", text)
        self.assertIn("--mode prepare", text)
        self.assertIn('ctx["network_allowed"] is False', text)
        self.assertIn("offline codex mock should not run in prepare mode", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
