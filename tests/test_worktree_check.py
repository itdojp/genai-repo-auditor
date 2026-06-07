from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class WorktreeCheckTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def git(self, repo: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def make_repo(self) -> Path:
        repo = self.work_dir / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.git(repo, "config", "user.email", "test@example.com")
        self.git(repo, "config", "user.name", "Test User")
        (repo / "README.md").write_text("# fixture\n", encoding="utf-8")
        self.git(repo, "add", "README.md")
        self.git(repo, "commit", "-m", "initial")
        return repo

    def test_worktree_check_classifies_unrelated_changes_and_writes_report(self) -> None:
        repo = self.make_repo()
        (repo / "docs").mkdir()
        (repo / "docs" / "guide.md").write_text("updated\n", encoding="utf-8")
        (repo / "reports").mkdir()
        (repo / "reports" / "raw.json").write_text("{}\n", encoding="utf-8")
        (repo / "scratch.txt").write_text("local\n", encoding="utf-8")
        out_md = self.work_dir / "worktree-final-check.md"

        cp = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "gra-worktree-check"),
                "--repo",
                str(repo),
                "--purpose",
                "auditor-maintenance",
                "--allowed-prefix",
                "docs",
                "--out-md",
                str(out_md),
                "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(1, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        report = json.loads(cp.stdout)
        self.assertEqual("auditor-maintenance", report["purpose"])
        self.assertEqual(["docs"], report["allowed_prefixes"])
        self.assertEqual(["docs/guide.md"], [item["path"] for item in report["in_scope_changes"]])
        self.assertEqual(["reports/raw.json", "scratch.txt"], sorted(item["path"] for item in report["unrelated_changes"]))
        report_md = out_md.read_text(encoding="utf-8")
        self.assertIn("## Unrelated changes", report_md)
        self.assertIn("reports/raw.json", report_md)
        self.assertIn("## Task ledger entry", report_md)

    def test_worktree_check_returns_zero_when_all_changes_are_in_scope(self) -> None:
        repo = self.make_repo()
        (repo / "docs").mkdir()
        (repo / "docs" / "guide.md").write_text("updated\n", encoding="utf-8")

        cp = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "gra-worktree-check"),
                "--repo",
                str(repo),
                "--purpose",
                "auditor-maintenance",
                "--allowed-prefix",
                "docs",
                "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(0, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        report = json.loads(cp.stdout)
        self.assertEqual([], report["unrelated_changes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
