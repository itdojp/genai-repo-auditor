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
from run_state import (  # noqa: E402
    paused_error,
    reports_dir,
    run_state_path,
    write_run_state,
)


class RunStateSafetyTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def make_run(self, reports_dir_value: object = "reports") -> Path:
        run_dir = self.work_dir / "run"
        run_dir.mkdir()
        (run_dir / "reports").mkdir()
        (run_dir / "context.json").write_text(
            json.dumps(
                {
                    "run_id": "run-state-test",
                    "repo": "example/repo",
                    "commit": "abc123",
                    "reports_dir": reports_dir_value,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return run_dir

    def test_reports_dir_rejects_paths_that_escape_run_directory(self) -> None:
        outside = self.work_dir / "outside"
        for unsafe in (str(outside.resolve()), "../outside", "reports/../outside"):
            with self.subTest(reports_dir=unsafe):
                run_dir = self.make_run(unsafe)
                with self.assertRaisesRegex(ValueError, "relative path under the run directory"):
                    reports_dir(run_dir)
                shutil.rmtree(run_dir)

    def test_reports_dir_rejects_symlink_components(self) -> None:
        outside = self.work_dir / "outside"
        outside.mkdir()
        run_dir = self.make_run("linked/reports")
        (run_dir / "linked").symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "must not contain symlink components"):
            run_state_path(run_dir)

    def test_write_run_state_does_not_follow_unsafe_reports_dir(self) -> None:
        outside = self.work_dir / "outside"
        outside.mkdir()
        run_dir = self.make_run(str(outside))

        with self.assertRaisesRegex(ValueError, "relative path under the run directory"):
            write_run_state(run_dir, {"status": "active"})
        self.assertFalse((outside / "run-state.json").exists())

    def test_paused_error_fail_closes_when_context_json_is_malformed(self) -> None:
        run_dir = self.make_run()
        (run_dir / "context.json").write_text("{not valid json", encoding="utf-8")

        message = paused_error(run_dir, action="target research for TGT-001")

        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("Refusing to start target research for TGT-001", message)
        self.assertIn("run state could not be read safely", message)
        self.assertIn(str(run_dir / "reports" / "run-state.json"), message)


if __name__ == "__main__":
    unittest.main()
