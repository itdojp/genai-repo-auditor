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

from scanner_reporting import (  # noqa: E402
    MAX_SCANNER_RUNS,
    ScannerReportError,
    append_scanner_run,
    build_scanner_run_record,
    preflight_scanner_reports,
)
from validators.common import load_schema, validate_schema  # noqa: E402
from validators.advanced import validate_scanner_runs  # noqa: E402


class ScannerReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))
        self.run_dir = self.work_dir / "run"
        self.run_dir.mkdir()
        (self.run_dir / "context.json").write_text(
            json.dumps({"run_id": "fixture-run", "repo": "example/demo", "reports_dir": "reports"}) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def record(self, **overrides):
        values = {
            "adapter_id": "gitleaks",
            "tool_version": "8.30.1",
            "image": "ghcr.io/gitleaks/gitleaks@sha256:" + "a" * 64,
            "status": "succeeded",
            "scanner_status": "completed-with-leads",
            "started_at": "2026-07-11T00:00:00Z",
            "ended_at": "2026-07-11T00:00:01Z",
            "duration_ms": 1000,
            "scanner_exit_code": 10,
            "result_count": 1,
            "normalized_leads_count": 1,
            "redaction_count": 1,
            "sandbox_profile": "container",
            "runtime": "docker",
            "network_accessed": False,
            "result_classification": "scanner-leads",
            "normalized_result_ref": None,
            "scanner_index_ref": None,
        }
        values.update(overrides)
        return build_scanner_run_record(**values)

    def test_writes_bounded_public_safe_json_and_markdown(self) -> None:
        report, json_path, markdown_path = append_scanner_run(self.run_dir, self.record())
        self.assertTrue(json_path.is_file())
        self.assertTrue(markdown_path.is_file())
        self.assertEqual(1, report["summary"]["run_count"])
        self.assertEqual(1000, report["summary"]["total_duration_ms"])
        self.assertEqual(1, report["summary"]["redaction_count"])
        self.assertTrue(report["safety"]["public_safe"])
        self.assertFalse(report["safety"]["raw_scanner_bodies_copied"])
        self.assertNotIn("raw_output", json_path.read_text(encoding="utf-8"))

        errors: list[str] = []
        validate_schema(report, load_schema(REPO_ROOT, "scanner-runs.schema.json"), "scanner_runs", errors)
        self.assertEqual([], errors)

    def test_rejects_secret_like_metadata_and_full_report(self) -> None:
        with self.assertRaisesRegex(ScannerReportError, "unredacted secret"):
            self.record(scanner_status="ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890")

    def test_rejects_raw_or_noncanonical_artifact_references(self) -> None:
        with self.assertRaisesRegex(ScannerReportError, "normalized scanner artifact"):
            self.record(normalized_result_ref="reports/scanner-results/raw/gitleaks.json")
        with self.assertRaisesRegex(ScannerReportError, "scanner-index.json"):
            self.record(scanner_index_ref="reports/scanner-results/raw/gitleaks.json")

    def test_validator_uses_configured_reports_dir_and_requires_canonical_index(self) -> None:
        context_path = self.run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "artifacts"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")
        scanner_results = self.run_dir / "artifacts" / "scanner-results"
        normalized = scanner_results / "normalized" / "gitleaks-leads.json"
        normalized.parent.mkdir(parents=True)
        normalized.write_text('{"leads": []}\n', encoding="utf-8")
        scanner_index = scanner_results / "scanner-index.json"
        scanner_index.write_text('{"results": []}\n', encoding="utf-8")
        record = self.record(
            normalized_result_ref="artifacts/scanner-results/normalized/gitleaks-leads.json",
            scanner_index_ref="artifacts/scanner-results/scanner-index.json",
        )
        mismatched_record = self.record(
            normalized_result_ref="artifacts/scanner-results/normalized/gitleaks-leads.json",
            scanner_index_ref="reports/scanner-results/scanner-index.json",
        )
        with self.assertRaisesRegex(ScannerReportError, "artifacts/scanner-results/scanner-index.json"):
            append_scanner_run(self.run_dir, mismatched_record)
        report, report_path, _ = append_scanner_run(self.run_dir, record)

        errors: list[str] = []
        self.assertTrue(validate_scanner_runs(self.run_dir, errors))
        self.assertEqual([], errors)

        raw_path = scanner_results / "raw" / "gitleaks.json"
        raw_path.parent.mkdir()
        raw_path.write_text("[]\n", encoding="utf-8")
        report["runs"][0]["scanner_index_ref"] = "artifacts/scanner-results/raw/gitleaks.json"
        report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
        errors = []
        self.assertTrue(validate_scanner_runs(self.run_dir, errors))
        self.assertTrue(any("scanner_index_ref: must reference" in error for error in errors), errors)

    def test_preflight_rejects_symlink_and_record_limit(self) -> None:
        reports = self.run_dir / "reports"
        reports.mkdir()
        outside = self.work_dir / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        report_path = reports / "scanner-runs.json"
        try:
            report_path.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaisesRegex(ScannerReportError, "symlink"):
            preflight_scanner_reports(self.run_dir)
        report_path.unlink()
        report_path.write_text(json.dumps({"runs": [{}] * MAX_SCANNER_RUNS}) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ScannerReportError, "limited"):
            preflight_scanner_reports(self.run_dir)


if __name__ == "__main__":
    unittest.main(verbosity=2)
