from __future__ import annotations

import contextlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from gralib import load_findings, load_targets, write_targets  # noqa: E402


class GralibPathSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))
        self.run_dir = self.work_dir / "run"
        self.run_dir.mkdir()
        (self.run_dir / "context.json").write_text(
            json.dumps({"reports_dir": "../outside"}) + "\n",
            encoding="utf-8",
        )
        self.outside = self.work_dir / "outside"
        self.outside.mkdir()
        (self.outside / "findings.json").write_text('{"findings": [{"id": "OUTSIDE"}]}\n', encoding="utf-8")
        (self.outside / "targets.json").write_text('{"targets": [{"id": "OUTSIDE"}]}\n', encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def test_report_loaders_and_writer_reject_unsafe_reports_dir(self) -> None:
        with self.assertRaisesRegex(OSError, "reports_dir must be a relative path"):
            load_findings(self.run_dir)
        with self.assertRaisesRegex(OSError, "reports_dir must be a relative path"):
            load_targets(self.run_dir)
        with self.assertRaisesRegex(OSError, "reports_dir must be a relative path"):
            write_targets(self.run_dir, [])

        self.assertEqual('{"findings": [{"id": "OUTSIDE"}]}\n', (self.outside / "findings.json").read_text())
        self.assertEqual('{"targets": [{"id": "OUTSIDE"}]}\n', (self.outside / "targets.json").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
