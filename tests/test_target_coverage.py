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
FIXTURES = REPO_ROOT / "tests" / "fixtures"

sys.path.insert(0, str(REPO_ROOT / "lib"))
from gralib import write_targets  # noqa: E402
from target_coverage import next_gapfill_targets, target_summary  # noqa: E402
from target_coverage_guardrails import (  # noqa: E402
    CoverageSerializationError,
    normalize_review_depth,
    normalize_targets_coverage_for_write,
)


class TargetCoverageGuardrailTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def make_run(self) -> Path:
        run_dir = self.work_dir / "run"
        run_dir.mkdir()
        (run_dir / "reports").mkdir()
        context = {
            "run_id": "test-run",
            "repo": "example/repo",
            "branch": "main",
            "commit": "abc123",
            "reports_dir": "reports",
        }
        (run_dir / "context.json").write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        return run_dir

    def copy_minimal_run(self) -> Path:
        run_dir = self.work_dir / "minimal-run"
        shutil.copytree(FIXTURES / "minimal-run", run_dir)
        return run_dir

    def target(self, review_depth: object) -> dict:
        return {
            "id": "TGT-001",
            "category": "fixture",
            "title": "Fixture target",
            "risk": "high",
            "priority": 90,
            "status": "reviewed",
            "scope": "repo/src/app.py",
            "entry_points": ["repo/src/app.py"],
            "trust_boundaries": ["local fixture"],
            "sinks": ["fixture sink"],
            "review_questions": ["fixture question"],
            "recommended_mode": "exec",
            "coverage": {
                "review_depth": review_depth,
                "files_reviewed": ["repo/src/app.py"],
                "files_skipped": [],
                "commands_run": [],
                "unresolved_questions": [],
                "gapfill_recommended": False,
                "gapfill_reason": "fixture complete",
            },
        }

    def test_normalize_review_depth_accepts_allowed_values_and_aliases(self) -> None:
        self.assertEqual(("deep", None), normalize_review_depth("deep", field_path="coverage.review_depth"))
        self.assertEqual(
            ("deep", "normalized coverage.review_depth alias 'bounded-deep' -> 'deep'"),
            normalize_review_depth("bounded-deep", field_path="coverage.review_depth"),
        )
        self.assertEqual(
            ("deep", "normalized coverage.review_depth alias 'bounded_deep' -> 'deep'"),
            normalize_review_depth("bounded_deep", field_path="coverage.review_depth"),
        )
        self.assertEqual(
            ("deep", "canonicalized coverage.review_depth value 'Deep' -> 'deep'"),
            normalize_review_depth("Deep", field_path="coverage.review_depth"),
        )

    def test_normalize_review_depth_rejects_unknown_values(self) -> None:
        with self.assertRaisesRegex(CoverageSerializationError, "invalid review depth 'broad'"):
            normalize_review_depth("broad", field_path="targets.targets[0].coverage.review_depth")
        with self.assertRaisesRegex(CoverageSerializationError, "must be a non-empty string"):
            normalize_review_depth("", field_path="targets.targets[0].coverage.review_depth")

    def test_write_targets_normalizes_review_depth_alias_and_logs(self) -> None:
        run_dir = self.make_run()
        write_targets(run_dir, [self.target("bounded-deep")])

        targets = json.loads((run_dir / "reports" / "targets.json").read_text(encoding="utf-8"))
        self.assertEqual("deep", targets["targets"][0]["coverage"]["review_depth"])

        jsonl_path = run_dir / "reports" / "coverage-normalizations.jsonl"
        self.assertTrue(jsonl_path.exists())
        events = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual("write_targets", events[0]["source"])
        self.assertEqual("TGT-001", events[0]["target_id"])
        self.assertEqual("bounded-deep", events[0]["before"])
        self.assertEqual("deep", events[0]["after"])

        audit_log = (run_dir / "reports" / "AUDIT_LOG.md").read_text(encoding="utf-8")
        self.assertIn("Coverage normalization", audit_log)
        self.assertIn("`bounded-deep` -> `deep`", audit_log)

    def test_write_targets_prevents_validator_review_depth_failure_fixture(self) -> None:
        run_dir = self.copy_minimal_run()
        target = self.target("bounded-deep")
        target["status"] = "queued"
        write_targets(run_dir, [target])

        cp = subprocess.run(
            [sys.executable, REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertEqual(cp.returncode, 0, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        data = json.loads((run_dir / "reports" / "targets.json").read_text(encoding="utf-8"))
        self.assertEqual("deep", data["targets"][0]["coverage"]["review_depth"])

    def test_write_targets_rejects_invalid_review_depth_without_overwriting_existing_file(self) -> None:
        run_dir = self.make_run()
        write_targets(run_dir, [self.target("shallow")])
        original = (run_dir / "reports" / "targets.json").read_text(encoding="utf-8")

        with self.assertRaisesRegex(CoverageSerializationError, "invalid review depth 'broad'"):
            write_targets(run_dir, [self.target("broad")])

        self.assertEqual(original, (run_dir / "reports" / "targets.json").read_text(encoding="utf-8"))

    def test_normalize_targets_coverage_for_write_reports_field_paths(self) -> None:
        normalized, changes = normalize_targets_coverage_for_write([self.target("bounded deep")])
        self.assertEqual("deep", normalized[0]["coverage"]["review_depth"])
        self.assertEqual("targets.targets[0].coverage.review_depth", changes[0]["field_path"])
        self.assertEqual("TGT-001", changes[0]["target_id"])

    def test_next_gapfill_targets_are_prioritized_with_relationship_context(self) -> None:
        targets = [
            {
                "id": "TGT-001",
                "priority": 50,
                "coverage": {"gapfill_reason": "source one needs more review"},
            },
            {
                "id": "TGT-002",
                "priority": 95,
                "coverage": {"gapfill_reason": "source two needs more review"},
            },
            {
                "id": "TGT-GAPFILL-001",
                "category": "gapfill",
                "source_target_id": "TGT-001",
                "priority": 50,
                "status": "in_progress",
            },
            {
                "id": "TGT-GAPFILL-002",
                "category": "gapfill",
                "source_target_id": "TGT-002",
                "priority": 95,
                "status": "queued",
                "variant_target_id": "TGT-GAPFILL-OLD",
            },
            {
                "id": "TGT-GAPFILL-003",
                "category": "gapfill",
                "source_target_id": "TGT-003",
                "priority": 100,
                "status": "reviewed",
            },
        ]

        next_targets = next_gapfill_targets(targets)

        self.assertEqual(["TGT-GAPFILL-002", "TGT-GAPFILL-001"], [item["target_id"] for item in next_targets])
        self.assertEqual("TGT-002", next_targets[0]["source_target_id"])
        self.assertEqual("variant", next_targets[0]["relationship"])
        self.assertEqual("source two needs more review", next_targets[0]["gapfill_reason"])

    def test_target_summary_preserves_variant_and_duplicate_alias_fields(self) -> None:
        source = self.target("shallow")

        variant_summary = target_summary(
            source,
            {
                "id": "TGT-GAPFILL-001",
                "status": "queued",
                "variant_target_id": "TGT-GAPFILL-OLD",
            },
        )
        self.assertEqual("variant", variant_summary["relationship"])
        self.assertEqual("TGT-GAPFILL-OLD", variant_summary["variant_of"])

        duplicate_summary = target_summary(
            source,
            {
                "id": "TGT-GAPFILL-002",
                "status": "queued",
                "duplicate_target_id": "TGT-GAPFILL-DUP",
            },
        )
        self.assertEqual("duplicate", duplicate_summary["relationship"])
        self.assertEqual("TGT-GAPFILL-DUP", duplicate_summary["duplicate_of"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
