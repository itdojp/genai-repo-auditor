from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))
import report_freshness as freshness  # noqa: E402


class ReportFreshnessTests(unittest.TestCase):
    def make_run(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        run_dir = Path(temporary.name) / "run"
        (run_dir / "reports").mkdir(parents=True)
        (run_dir / "context.json").write_text(
            json.dumps({"run_id": "run", "reports_dir": "reports", "target_repo_dir": "repo"}) + "\n",
            encoding="utf-8",
        )
        return temporary, run_dir

    def write_metrics_outputs(self, run_dir: Path) -> None:
        (run_dir / "reports" / "metrics.json").write_text("{}\n", encoding="utf-8")
        (run_dir / "reports" / "METRICS.md").write_text("# Metrics\n", encoding="utf-8")

    def test_unchanged_dependency_is_fresh(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        self.write_metrics_outputs(run_dir)
        (run_dir / "reports" / "findings.json").write_text("{}\n", encoding="utf-8")

        freshness.record_artifact(
            run_dir,
            "metrics",
            [freshness.dependency("reports/findings.json", required=True)],
            producer_version="0.5.0",
        )

        summary = freshness.assess_freshness(run_dir)
        metrics = next(item for item in summary["artifacts"] if item["artifact_id"] == "metrics")
        self.assertEqual(metrics["status"], "fresh")
        self.assertEqual(summary["counts"]["fresh"], 1)

    def test_changed_dependency_is_stale(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        self.write_metrics_outputs(run_dir)
        source = run_dir / "reports" / "findings.json"
        source.write_text("{\"count\": 1}\n", encoding="utf-8")
        freshness.record_artifact(
            run_dir,
            "metrics",
            [freshness.dependency("reports/findings.json", required=True)],
        )

        source.write_text("{\"count\": 2}\n", encoding="utf-8")
        metrics = next(
            item for item in freshness.assess_freshness(run_dir)["artifacts"] if item["artifact_id"] == "metrics"
        )
        self.assertEqual(metrics["status"], "stale")
        self.assertEqual(metrics["stale_dependency_refs"], ["reports/findings.json"])

    def test_issue_dry_run_pair_is_tracked_by_metrics_and_dashboard(self) -> None:
        for artifact_id in ("metrics", "dashboard"):
            with self.subTest(artifact_id=artifact_id):
                temporary, run_dir = self.make_run()
                self.addCleanup(temporary.cleanup)
                reports = run_dir / "reports"
                (reports / "findings.json").write_text("{}\n", encoding="utf-8")
                (reports / "issue-dry-run-summary.json").write_text("{}\n", encoding="utf-8")
                markdown = reports / "ISSUE_DRY_RUN_SUMMARY.md"
                markdown.write_text("# Initial\n", encoding="utf-8")
                for name in freshness.ARTIFACT_CATALOG[artifact_id].output_names:
                    (reports / name).write_text("generated\n", encoding="utf-8")

                dependencies = freshness.artifact_dependencies(run_dir, artifact_id)
                refs = {item["artifact_ref"] for item in dependencies}
                self.assertIn("reports/issue-dry-run-summary.json", refs)
                self.assertIn("reports/ISSUE_DRY_RUN_SUMMARY.md", refs)
                freshness.record_artifact(run_dir, artifact_id, dependencies)

                markdown.write_text("# Changed\n", encoding="utf-8")
                status = next(
                    item
                    for item in freshness.assess_freshness(run_dir)["artifacts"]
                    if item["artifact_id"] == artifact_id
                )
                self.assertEqual("stale", status["status"])
                self.assertIn(
                    "reports/ISSUE_DRY_RUN_SUMMARY.md",
                    status["stale_dependency_refs"],
                )

        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        benchmark_refs = {
            item["artifact_ref"]
            for item in freshness.artifact_dependencies(run_dir, "benchmark")
        }
        self.assertIn("reports/issue-dry-run-summary.json", benchmark_refs)
        self.assertIn("reports/ISSUE_DRY_RUN_SUMMARY.md", benchmark_refs)

    def test_optional_absence_is_fresh_and_later_presence_is_stale(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        self.write_metrics_outputs(run_dir)
        freshness.record_artifact(
            run_dir,
            "metrics",
            [freshness.dependency("reports/benchmark.json")],
        )
        before = next(
            item for item in freshness.assess_freshness(run_dir)["artifacts"] if item["artifact_id"] == "metrics"
        )
        self.assertEqual(before["status"], "fresh")

        (run_dir / "reports" / "benchmark.json").write_text("{}\n", encoding="utf-8")
        after = next(
            item for item in freshness.assess_freshness(run_dir)["artifacts"] if item["artifact_id"] == "metrics"
        )
        self.assertEqual(after["status"], "stale")

    def test_every_catalog_entry_requires_context(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)

        for artifact_id in freshness.ARTIFACT_CATALOG:
            with self.subTest(artifact_id=artifact_id):
                context = next(
                    item
                    for item in freshness.artifact_dependencies(run_dir, artifact_id)
                    if item["artifact_ref"] == "context.json"
                )
                self.assertEqual(context["requirement"], "required")

    def test_fallback_closes_leaf_when_fstat_fails(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        source = run_dir / "reports" / "findings.json"
        source.write_text("{}\n", encoding="utf-8")
        real_close = freshness.os.close
        closed_fds: list[int] = []

        def record_close(fd: int) -> None:
            closed_fds.append(fd)
            real_close(fd)

        with (
            unittest.mock.patch.object(freshness.os, "supports_dir_fd", set()),
            unittest.mock.patch.object(freshness.os, "fstat", side_effect=OSError("forced fstat failure")),
            unittest.mock.patch.object(freshness.os, "close", side_effect=record_close),
            self.assertRaisesRegex(OSError, "forced fstat failure"),
        ):
            freshness._open_ref_fd(run_dir, "reports/findings.json", allow_missing=False)

        self.assertEqual(len(closed_fds), 1)

    @unittest.skipUnless(
        freshness.os.open in getattr(freshness.os, "supports_dir_fd", set())
        and bool(getattr(freshness.os, "O_DIRECTORY", 0)),
        "requires POSIX dir_fd directory walk",
    )
    def test_posix_walk_closes_directories_and_leaf_when_fstat_fails(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        source = run_dir / "reports" / "findings.json"
        source.write_text("{}\n", encoding="utf-8")
        real_close = freshness.os.close
        closed_fds: list[int] = []

        def record_close(fd: int) -> None:
            closed_fds.append(fd)
            real_close(fd)

        with (
            unittest.mock.patch.object(freshness.os, "fstat", side_effect=OSError("forced fstat failure")),
            unittest.mock.patch.object(freshness.os, "close", side_effect=record_close),
            self.assertRaisesRegex(OSError, "forced fstat failure"),
        ):
            freshness._open_ref_fd(run_dir, "reports/findings.json", allow_missing=False)

        self.assertEqual(len(closed_fds), 3)

    def test_removed_captured_dependency_is_missing(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        self.write_metrics_outputs(run_dir)
        source = run_dir / "reports" / "findings.json"
        source.write_text("{}\n", encoding="utf-8")
        freshness.record_artifact(
            run_dir,
            "metrics",
            [freshness.dependency("reports/findings.json", required=True)],
        )
        source.unlink()

        metrics = next(
            item for item in freshness.assess_freshness(run_dir)["artifacts"] if item["artifact_id"] == "metrics"
        )
        self.assertEqual(metrics["status"], "missing_dependency")
        self.assertEqual(metrics["missing_dependency_refs"], ["reports/findings.json"])

    def test_legacy_output_without_sidecar_is_not_applicable(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        self.write_metrics_outputs(run_dir)
        summary = freshness.assess_freshness(run_dir)
        self.assertEqual(summary["overall_status"], "not_applicable")
        self.assertEqual(summary["counts"]["not_applicable"], len(freshness.ARTIFACT_CATALOG))

    def test_absolute_parent_and_symlink_refs_fail_closed(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        self.write_metrics_outputs(run_dir)
        outside = Path(temporary.name) / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        (run_dir / "reports" / "link.json").symlink_to(outside)

        for ref in (str(outside), "C:/outside.json", "../outside.json", "reports/link.json"):
            with self.subTest(ref=ref), self.assertRaises(freshness.FreshnessError):
                freshness.record_artifact(run_dir, "metrics", [freshness.dependency(ref)])
        for ref in ("prompts/worker.md", "reports/ghp_abcdefghijklmnopqrstuvwxyz.json"):
            with self.subTest(ref=ref), self.assertRaises(freshness.FreshnessError):
                freshness.dependency(ref)

    def test_oversized_dependency_fails_closed(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        self.write_metrics_outputs(run_dir)
        source = run_dir / "reports" / "large.json"
        with source.open("wb") as handle:
            handle.truncate(freshness.MAX_INPUT_BYTES + 1)
        with self.assertRaisesRegex(freshness.FreshnessError, "exceeds"):
            freshness.record_artifact(run_dir, "metrics", [freshness.dependency("reports/large.json")])

    def test_duplicate_and_output_overlap_fail_closed(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        self.write_metrics_outputs(run_dir)
        source = run_dir / "reports" / "findings.json"
        source.write_text("{}\n", encoding="utf-8")
        duplicate = freshness.dependency("reports/findings.json")
        with self.assertRaisesRegex(freshness.FreshnessError, "duplicate"):
            freshness.record_artifact(run_dir, "metrics", [duplicate, duplicate])
        with self.assertRaisesRegex(freshness.FreshnessError, "overlap"):
            freshness.record_artifact(run_dir, "metrics", [freshness.dependency("reports/metrics.json")])
        with self.assertRaisesRegex(freshness.FreshnessError, "overlap"):
            freshness.record_artifact(
                run_dir,
                "metrics",
                [freshness.dependency("reports/missing"), freshness.dependency("reports/missing/value.json")],
            )

    def test_poisoned_sidecar_is_rejected(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        path = run_dir / "reports" / freshness.FRESHNESS_FILE
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1",
                    "generated_at": "2026-07-18T00:00:00Z",
                    "source": "genai-repo-auditor",
                    "records": [{"artifact_id": "unknown"}],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(freshness.FreshnessError):
            freshness.assess_freshness(run_dir)

    def test_dependency_change_between_preflight_and_record_fails_closed(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        self.write_metrics_outputs(run_dir)
        source = run_dir / "reports" / "findings.json"
        source.write_text("{\"count\": 1}\n", encoding="utf-8")
        captured = freshness.preflight_artifact_dependencies(
            run_dir,
            "metrics",
            [freshness.dependency("reports/findings.json", required=True)],
        )
        source.write_text("{\"count\": 2}\n", encoding="utf-8")

        with self.assertRaisesRegex(freshness.FreshnessError, "changed during report generation"):
            freshness.record_artifact(run_dir, "metrics", captured)

    def test_dynamic_discovery_fails_closed_before_unbounded_collection(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        root = run_dir / "reports" / "scanner-readiness"
        root.mkdir()
        for index in range(freshness.MAX_DISCOVERY_ENTRIES + 1):
            (root / f"unrelated-{index:04d}.txt").write_text("x\n", encoding="utf-8")

        with self.assertRaisesRegex(freshness.FreshnessError, "discovery exceeds"):
            freshness.artifact_dependencies(run_dir, "metrics")

    def test_benchmark_discovery_is_bounded_before_sorting(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        for index in range(freshness.MAX_DISCOVERY_ENTRIES + 1):
            (run_dir / "reports" / f"noise-{index:04d}.txt").write_text("x\n", encoding="utf-8")

        with self.assertRaisesRegex(freshness.FreshnessError, "discovery exceeds"):
            freshness.artifact_dependencies(run_dir, "benchmark")

    def test_bounded_json_loader_rejects_oversize_and_symlink(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        marker = run_dir / "reports" / "store-import-state.json"
        marker.write_text("{\"value\": \"0123456789\"}\n", encoding="utf-8")
        with self.assertRaisesRegex(freshness.FreshnessError, "exceeds"):
            freshness.load_bounded_json_artifact(
                run_dir,
                "reports/store-import-state.json",
                max_bytes=8,
            )
        marker.unlink()
        outside = Path(temporary.name) / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        marker.symlink_to(outside)
        with self.assertRaises(freshness.FreshnessError):
            freshness.load_bounded_json_artifact(run_dir, "reports/store-import-state.json")

    def test_embedded_summary_rejects_inconsistent_overall_status(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        summary = freshness.public_summary(freshness.assess_freshness(run_dir))
        summary["overall_status"] = "fresh"

        with self.assertRaisesRegex(freshness.FreshnessError, "overall status"):
            freshness.validate_public_summary(summary)

    def test_dynamic_matching_directory_fails_closed_as_non_file(self) -> None:
        temporary, run_dir = self.make_run()
        self.addCleanup(temporary.cleanup)
        (run_dir / "reports" / "findings.json").write_text("{}\n", encoding="utf-8")
        (run_dir / "reports" / "scanner-readiness" / "poison.json").mkdir(parents=True)

        with self.assertRaisesRegex(freshness.FreshnessError, "regular"):
            freshness.preflight_artifact_dependencies(
                run_dir,
                "metrics",
                freshness.artifact_dependencies(run_dir, "metrics"),
            )


if __name__ == "__main__":
    unittest.main()
