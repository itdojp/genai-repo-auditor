from __future__ import annotations

import contextlib
import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from scanner_ingest import build_scanner_ingest_plan, ingest_scanner_file  # noqa: E402


class ScannerIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def test_concurrent_ingestion_preserves_both_index_entries(self) -> None:
        run_dir = self.work_dir / "run"
        raw_dir = run_dir / "reports" / "scanner-results" / "raw"
        raw_dir.mkdir(parents=True)
        (run_dir / "context.json").write_text(
            json.dumps({"run_id": "fixture-run", "repo": "example/demo", "reports_dir": "reports"}) + "\n",
            encoding="utf-8",
        )
        gitleaks = raw_dir / "gitleaks.json"
        syft = raw_dir / "syft.json"
        gitleaks.write_text("[]\n", encoding="utf-8")
        syft.write_text(json.dumps({"bomFormat": "CycloneDX", "components": []}) + "\n", encoding="utf-8")
        plans = [
            build_scanner_ingest_plan(
                run_dir,
                tool="gitleaks",
                source=gitleaks,
                requested_format="json",
                managed_source=True,
            ),
            build_scanner_ingest_plan(
                run_dir,
                tool="syft",
                source=syft,
                requested_format="cyclonedx",
                managed_source=True,
            ),
        ]
        barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def ingest(plan) -> None:
            try:
                barrier.wait(timeout=5)
                ingest_scanner_file(plan)
            except Exception as exc:  # noqa: BLE001 - collect worker failure for the assertion.
                errors.append(exc)

        workers = [threading.Thread(target=ingest, args=(plan,)) for plan in plans]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        self.assertEqual([], errors)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        index = json.loads((run_dir / "reports" / "scanner-results" / "scanner-index.json").read_text(encoding="utf-8"))
        self.assertEqual(["gitleaks", "syft"], sorted(item["tool"] for item in index["results"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
