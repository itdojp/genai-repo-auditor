from __future__ import annotations

import contextlib
import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from gralib import MAX_TARGETS_JSON_BYTES, load_findings, load_targets, write_targets  # noqa: E402


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

    def use_safe_reports_dir(self) -> Path:
        (self.run_dir / "context.json").write_text(
            json.dumps({"run_id": "safe-run", "reports_dir": "reports", "target_repo_dir": "repo"}) + "\n",
            encoding="utf-8",
        )
        reports = self.run_dir / "reports"
        reports.mkdir(exist_ok=True)
        return reports

    def test_targets_loader_and_writer_reject_leaf_symlink_without_touching_destination(self) -> None:
        reports = self.use_safe_reports_dir()
        protected = self.work_dir / "protected.json"
        protected.write_text('{"protected": true}\n', encoding="utf-8")
        (reports / "targets.json").symlink_to(protected)

        with self.assertRaisesRegex(OSError, "regular non-symlink"):
            load_targets(self.run_dir)
        with self.assertRaisesRegex(OSError, "regular non-symlink"):
            write_targets(self.run_dir, [])

        self.assertEqual('{"protected": true}\n', protected.read_text(encoding="utf-8"))

    def test_targets_writer_is_atomic_when_replace_fails(self) -> None:
        reports = self.use_safe_reports_dir()
        targets_path = reports / "targets.json"
        original = '{"targets": []}\n'
        targets_path.write_text(original, encoding="utf-8")

        with mock.patch("gralib.os.replace", side_effect=OSError("fixture replace failure")):
            with self.assertRaisesRegex(OSError, "fixture replace failure"):
                write_targets(self.run_dir, [])

        self.assertEqual(original, targets_path.read_text(encoding="utf-8"))
        self.assertEqual([], list(reports.glob(".targets.json.*.tmp")))

    def test_targets_loader_rejects_oversized_file_before_json_parse(self) -> None:
        reports = self.use_safe_reports_dir()
        with (reports / "targets.json").open("wb") as stream:
            stream.truncate(MAX_TARGETS_JSON_BYTES + 1)

        with self.assertRaisesRegex(OSError, "exceeds the .*byte limit"):
            load_targets(self.run_dir)


if __name__ == "__main__":
    unittest.main(verbosity=2)
