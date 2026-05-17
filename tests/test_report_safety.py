from __future__ import annotations

import contextlib
import shutil
import tempfile
import unittest
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from report_safety import (  # noqa: E402
    MAX_ISSUE_BODY_BYTES,
    ReportSafetyError,
    iter_secret_findings,
    safe_issue_body_path,
    validate_relative_repo_path,
)


class ReportSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.run_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))
        self.drafts = self.run_dir / "reports" / "issue-drafts"
        self.drafts.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.run_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def write_draft(self, name: str = "SEC-001.md", text: str = "# Draft\n") -> Path:
        path = self.drafts / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def assert_safety_error(self, expected: str, value: object, **kwargs) -> None:
        with self.assertRaisesRegex(ReportSafetyError, expected):
            safe_issue_body_path(self.run_dir, value, **kwargs)

    def test_safe_issue_body_path_accepts_regular_markdown_under_issue_drafts(self) -> None:
        draft = self.write_draft("nested/SEC-001.md")
        resolved = safe_issue_body_path(self.run_dir, "reports/issue-drafts/nested/SEC-001.md")
        self.assertEqual(resolved, draft.resolve())

    def test_safe_issue_body_path_rejects_traversal_absolute_non_markdown_and_oversized_files(self) -> None:
        self.write_draft("SEC-001.md")
        self.assert_safety_error("must not contain", "reports/issue-drafts/../SEC-001.md")
        self.assert_safety_error("must be relative", "/reports/issue-drafts/SEC-001.md")
        self.assert_safety_error("must use '/' separators", r"reports\issue-drafts\SEC-001.md")

        txt = self.drafts / "SEC-001.txt"
        txt.write_text("not markdown\n", encoding="utf-8")
        self.assert_safety_error(r"must be a \.md file", "reports/issue-drafts/SEC-001.txt")

        oversized = self.drafts / "oversized.md"
        oversized.write_bytes(b"x" * (MAX_ISSUE_BODY_BYTES + 1))
        self.assert_safety_error("exceeds", "reports/issue-drafts/oversized.md")

    def test_safe_issue_body_path_rejects_file_and_parent_symlinks(self) -> None:
        outside = self.run_dir / "outside.md"
        outside.write_text("outside\n", encoding="utf-8")
        (self.drafts / "link.md").symlink_to(outside)
        self.assert_safety_error("must not be a symlink", "reports/issue-drafts/link.md")

        real_drafts = self.run_dir / "real-drafts"
        real_drafts.mkdir()
        (real_drafts / "SEC-002.md").write_text("# Draft\n", encoding="utf-8")
        symlink_parent = self.drafts / "linked-parent"
        symlink_parent.symlink_to(real_drafts, target_is_directory=True)
        self.assert_safety_error("must not be a symlink", "reports/issue-drafts/linked-parent/SEC-002.md")

    def test_validate_relative_repo_path_rejects_unsafe_paths(self) -> None:
        self.assertEqual(validate_relative_repo_path("src/app.py", field_path="loc.file"), "src/app.py")
        invalid = {
            "": "must not be empty",
            "../secret.py": "must not contain",
            "/etc/passwd": "must be relative",
            r"src\\app.py": "must use '/' separators",
            "~/secret.py": "must not use home-directory expansion",
            "src//app.py": "must not contain",
            "src/./app.py": "must not contain",
            "nul\x00byte.py": "contains NUL byte",
        }
        for value, expected in invalid.items():
            with self.subTest(value=value):
                with self.assertRaisesRegex(ReportSafetyError, expected):
                    validate_relative_repo_path(value, field_path="loc.file")

    def test_iter_secret_findings_detects_obvious_full_secrets_but_allows_marked_examples(self) -> None:
        report = {
            "safe": "AWS key REDACTED example AKIAABCDEFGHIJKLMNOP",
            "findings": [
                {"evidence": "token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"},
                {"nested": ["-----BEGIN PRIVATE KEY-----\nABCDEF"]},
                {"slack": "xoxb-abcdefghijklmnopqrstuvwxyz123456"},
            ],
        }
        errors = list(iter_secret_findings(report, field_path="report"))
        joined = "\n".join(errors)
        self.assertIn("GitHub token", joined)
        self.assertIn("private key", joined)
        self.assertIn("Slack token", joined)
        self.assertNotIn("report.safe", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
