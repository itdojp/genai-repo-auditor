from __future__ import annotations

import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout, suppress
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "clean-local-artifacts.py"


def load_cleanup_module():
    spec = importlib.util.spec_from_file_location("clean_local_artifacts", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"failed to load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LocalArtifactCleanupTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))
        self.runs_dir = self.work_dir / "runs"
        self.batches_dir = self.work_dir / "batches"

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with suppress(OSError):
            self.tmp_parent.rmdir()

    def run_cleaner(self, *args: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *[str(arg) for arg in args]],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )

    def create_artifacts(self) -> dict[str, Path]:
        run_dir = self.runs_dir / "example__demo" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "reports").mkdir()
        (run_dir / "reports" / "findings.json").write_text('{"findings": []}\n', encoding="utf-8")

        batch_dir = self.runs_dir / "_batches" / "batch-1"
        batch_dir.mkdir(parents=True)
        (batch_dir / "batch-results.json").write_text('{"results": []}\n', encoding="utf-8")

        store = self.runs_dir / "security-audit.sqlite"
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text("sqlite fixture\n", encoding="utf-8")

        legacy_batch = self.batches_dir / "legacy-batch"
        legacy_batch.mkdir(parents=True)
        (legacy_batch / "batch.log").write_text("legacy batch\n", encoding="utf-8")

        return {
            "run_dir": run_dir,
            "batch_dir": batch_dir,
            "store": store,
            "legacy_batch": legacy_batch,
        }

    def test_cleanup_script_is_executable(self) -> None:
        self.assertTrue(os.access(SCRIPT, os.X_OK), f"{SCRIPT} should be executable")

    def test_cleanup_defaults_to_dry_run_and_preserves_artifacts(self) -> None:
        paths = self.create_artifacts()
        cp = self.run_cleaner("--runs-dir", self.runs_dir, "--batches-dir", self.batches_dir)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("DRY RUN: would remove local artifacts:", cp.stdout)
        self.assertIn(".test-tmp/", cp.stdout)
        self.assertIn("run-1", cp.stdout)
        self.assertIn("security-audit.sqlite", cp.stdout)
        self.assertIn("legacy-batch", cp.stdout)
        self.assertIn("Re-run with --apply", cp.stdout)
        for path in paths.values():
            self.assertTrue(path.exists(), f"dry-run should preserve {path}")

    def test_cleanup_apply_removes_only_listed_local_artifacts(self) -> None:
        paths = self.create_artifacts()
        keep_file = self.runs_dir / ".locks" / "active.lock"
        keep_file.parent.mkdir(parents=True)
        keep_file.write_text("active lock\n", encoding="utf-8")

        cp = self.run_cleaner("--runs-dir", self.runs_dir, "--batches-dir", self.batches_dir, "--apply")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("Removing local artifacts:", cp.stdout)
        self.assertIn("Removed 4 artifact(s).", cp.stdout)
        for path in paths.values():
            self.assertFalse(path.exists(), f"apply should remove {path}")
        self.assertTrue(keep_file.exists(), "active lock files must not be removed by cleanup")

    def test_cleanup_deduplicates_overlapping_runs_and_batches_roots(self) -> None:
        paths = self.create_artifacts()
        cp = self.run_cleaner(
            "--runs-dir",
            self.runs_dir,
            "--batches-dir",
            self.runs_dir / "_batches",
            "--apply",
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("Removed 3 artifact(s).", cp.stdout)
        for path in [paths["run_dir"], paths["batch_dir"], paths["store"]]:
            self.assertFalse(path.exists(), f"apply should remove {path} once")
        self.assertTrue(paths["legacy_batch"].exists(), "non-selected legacy batches dir should remain")

    def test_cleanup_reports_removal_errors_without_traceback(self) -> None:
        paths = self.create_artifacts()
        module = load_cleanup_module()
        original_remove_candidate = module.remove_candidate

        def fail_for_store(candidate) -> None:
            if candidate.path == paths["store"].resolve():
                raise OSError("fixture removal failure")
            original_remove_candidate(candidate)

        module.remove_candidate = fail_for_store
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = module.main([
                "--runs-dir",
                str(self.runs_dir),
                "--batches-dir",
                str(self.batches_dir),
                "--apply",
            ])
        self.assertEqual(rc, 1)
        self.assertIn("Removed 3 artifact(s); 1 removal(s) failed.", stdout.getvalue())
        self.assertIn("ERROR: failed to remove file:", stderr.getvalue())
        self.assertIn("fixture removal failure", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertTrue(paths["store"].exists())

    def test_cleanup_refuses_paths_outside_repository(self) -> None:
        cp = self.run_cleaner("--runs-dir", "../outside-runs", "--batches-dir", self.batches_dir)
        self.assertEqual(cp.returncode, 2)
        self.assertIn("runs-dir must stay under repository root", cp.stderr)

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks require pathlib support")
    def test_cleanup_refuses_symlinked_base_and_candidates(self) -> None:
        outside = self.work_dir / "outside"
        outside.mkdir()
        symlinked_runs = self.work_dir / "symlinked-runs"
        symlinked_runs.symlink_to(outside, target_is_directory=True)

        cp_base = self.run_cleaner("--runs-dir", symlinked_runs, "--batches-dir", self.batches_dir)
        self.assertEqual(cp_base.returncode, 2)
        self.assertIn("runs-dir must not contain symlink components", cp_base.stderr)

        broken_runs = self.work_dir / "broken-runs"
        broken_runs.symlink_to(self.work_dir / "missing-target", target_is_directory=True)
        cp_broken_base = self.run_cleaner("--runs-dir", broken_runs, "--batches-dir", self.batches_dir)
        self.assertEqual(cp_broken_base.returncode, 2)
        self.assertIn("runs-dir must not contain symlink components", cp_broken_base.stderr)

        self.runs_dir.mkdir()
        owner = self.runs_dir / "example__demo"
        owner.mkdir()
        unsafe_run = owner / "run-link"
        unsafe_run.symlink_to(outside, target_is_directory=True)
        cp_candidate = self.run_cleaner("--runs-dir", self.runs_dir, "--batches-dir", self.batches_dir)
        self.assertEqual(cp_candidate.returncode, 2)
        self.assertIn("runs-dir candidate must not be a symlink", cp_candidate.stderr)

        unsafe_run.unlink()
        broken_run = owner / "broken-run-link"
        broken_run.symlink_to(self.work_dir / "missing-run", target_is_directory=True)
        cp_broken_candidate = self.run_cleaner("--runs-dir", self.runs_dir, "--batches-dir", self.batches_dir)
        self.assertEqual(cp_broken_candidate.returncode, 2)
        self.assertIn("runs-dir candidate must not be a symlink", cp_broken_candidate.stderr)


if __name__ == "__main__":
    unittest.main()
