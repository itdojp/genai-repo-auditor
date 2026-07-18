from __future__ import annotations

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403

from report_freshness import ARTIFACT_CATALOG, assess_freshness  # noqa: E402


class ReportFreshnessWorkflowTests(CliWorkflowTestCase):
    def test_legacy_run_without_sidecar_is_not_applicable_even_with_freshness_check(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        cp = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir, "--check-freshness"],
            check=True,
        )
        self.assertIn("Report freshness status: not_applicable", cp.stdout)
        self.assertFalse((run_dir / "reports" / "report-freshness.json").exists())

    def test_metrics_records_fresh_dependencies_and_validation_is_opt_in_for_staleness(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)

        sidecar_path = run_dir / "reports" / "report-freshness.json"
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        self.assertEqual("1", sidecar["schema_version"])
        self.assertEqual(["metrics"], [item["artifact_id"] for item in sidecar["records"]])
        self.assertFalse(any(Path(item["artifact_ref"]).is_absolute() for item in sidecar["records"][0]["dependencies"]))
        metrics = json.loads((run_dir / "reports" / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual("fresh", metrics["report_freshness"]["overall_status"])
        self.assertEqual("fresh", assess_freshness(run_dir)["overall_status"])

        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"][0]["title"] = "Changed after metrics generation"
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")
        sidecar_before = sidecar_path.read_bytes()

        structural = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertEqual(0, structural.returncode, structural.stderr)
        freshness = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir, "--check-freshness"]
        )
        self.assertEqual(1, freshness.returncode)
        self.assertIn("report_freshness.metrics: status is stale", freshness.stderr)
        self.assertIn("gra-metrics --run <run_dir>", freshness.stderr)
        self.assertEqual(sidecar_before, sidecar_path.read_bytes(), "validation must not regenerate or rewrite reports")

    def test_safe_regeneration_order_converges_and_store_marker_excludes_database_path(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        database = self.work_dir / "local.sqlite"
        commands = [
            [REPO_ROOT / "bin" / "gra-sarif", "--run", run_dir],
            [REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--plan"],
            [REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", database],
            [REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir],
            [REPO_ROOT / "bin" / "gra-evidence-graph", "--run", run_dir],
            [REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir],
            [REPO_ROOT / "bin" / "gra-benchmark", "--run", run_dir, "--skip-validation"],
            [REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir],
            [REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir],
        ]
        for command in commands:
            self.run_cmd(command, check=True)

        tracked_commands = {
            "gra-sarif",
            "gra-issues",
            "gra-store",
            "gra-metrics",
            "gra-benchmark",
            "gra-evidence-graph",
            "gra-dashboard",
        }
        events = [event for event in self.read_command_events(run_dir) if event["command"] in tracked_commands]
        self.assertTrue(tracked_commands.issubset({event["command"] for event in events}))
        for event in events:
            self.assertIn("reports/report-freshness.json", event["output_artifact_refs"], event)

        summary = assess_freshness(run_dir)
        self.assertEqual("fresh", summary["overall_status"])
        self.assertEqual(len(ARTIFACT_CATALOG), summary["counts"]["fresh"])
        self.assertTrue(all(item["status"] == "fresh" for item in summary["artifacts"]))
        validated = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir, "--check-freshness"],
            check=True,
        )
        self.assertIn("Report freshness status: fresh", validated.stdout)

        marker_text = (run_dir / "reports" / "store-import-state.json").read_text(encoding="utf-8")
        marker = json.loads(marker_text)
        self.assertFalse(marker["database_location_recorded"])
        self.assertNotIn(str(database), marker_text)
        self.assertNotIn("local.sqlite", marker_text)
        store_result = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", database],
            check=True,
        )
        self.assertNotIn(str(database), store_result.stdout)
        self.assertNotIn("local.sqlite", store_result.stdout)
        dashboard = (run_dir / "reports" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Derived report freshness", dashboard)
        self.assertIn("Overall status: <code>fresh</code>", dashboard)

    def test_default_publication_plan_rejects_stale_source_even_when_parsed_findings_are_unchanged(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.run_cmd([REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--plan"], check=True)
        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertIn("report_freshness", plan)
        self.assertEqual("fresh", plan["report_freshness"]["artifacts"][2]["status"])

        findings_path = run_dir / "reports" / "findings.json"
        findings_path.write_text(findings_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
                "--dry-run",
            ]
        )
        self.assertEqual(4, cp.returncode)
        self.assertIn("issue publication plan freshness is stale", cp.stderr)
        self.assertIn("review it before applying", cp.stderr)

    def test_copied_publication_plan_cannot_bypass_tracked_freshness_gate(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.run_cmd([REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--plan"], check=True)
        default_plan = run_dir / "reports" / "issue-publication-plan.json"
        copied_plan = run_dir / "reports" / "reviewed-plan-copy.json"
        shutil.copy2(default_plan, copied_plan)

        findings_path = run_dir / "reports" / "findings.json"
        findings_path.write_text(findings_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                copied_plan,
                "--dry-run",
            ]
        )

        self.assertEqual(4, cp.returncode)
        self.assertIn("issue publication plan freshness is stale", cp.stderr)

    def test_publication_apply_fails_closed_when_tracking_sidecar_or_record_is_removed(self) -> None:
        for mutation in ("delete-sidecar", "strip-plan-record"):
            with self.subTest(mutation=mutation):
                run_dir = self.copy_fixture_run("minimal-run")
                self.run_cmd([REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--plan"], check=True)
                plan_path = run_dir / "reports" / "issue-publication-plan.json"
                sidecar_path = run_dir / "reports" / "report-freshness.json"
                if mutation == "delete-sidecar":
                    sidecar_path.unlink()
                else:
                    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
                    sidecar["records"] = [
                        item for item in sidecar["records"] if item["artifact_id"] != "issue_publication_plan"
                    ]
                    sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")

                cp = self.run_cmd(
                    [
                        REPO_ROOT / "bin" / "gra-issues",
                        "--run",
                        run_dir,
                        "--apply-plan",
                        plan_path,
                        "--dry-run",
                    ]
                )

                self.assertEqual(4, cp.returncode)
                self.assertIn("freshness tracking is unavailable", cp.stderr)
                self.assertIn("review it before applying", cp.stderr)

    def test_custom_path_replan_fails_before_writing_an_untracked_plan(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        custom_plan = run_dir / "reports" / "custom-plan.json"

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                custom_plan,
                "--replan",
                "--dry-run",
            ]
        )

        self.assertEqual(4, cp.returncode)
        self.assertIn("custom-path replan cannot establish tracked freshness", cp.stderr)
        self.assertFalse(custom_plan.exists())

    def test_publication_plan_tracks_the_legacy_repo_findings_fallback(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        source = run_dir / "reports" / "findings.json"
        fallback = run_dir / "repo" / ".genai-audit" / "reports" / "findings.json"
        fallback.parent.mkdir(parents=True)
        source.replace(fallback)

        self.run_cmd([REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--plan"], check=True)
        sidecar = json.loads((run_dir / "reports" / "report-freshness.json").read_text(encoding="utf-8"))
        plan_record = next(item for item in sidecar["records"] if item["artifact_id"] == "issue_publication_plan")
        refs = [item["artifact_ref"] for item in plan_record["dependencies"]]
        self.assertIn("repo/.genai-audit/reports/findings.json", refs)
        self.assertNotIn("reports/findings.json", refs)

    def test_store_marker_validator_rejects_path_fields_without_echoing_values(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        database = self.work_dir / "private-store.sqlite"
        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", database],
            check=True,
        )
        marker_path = run_dir / "reports" / "store-import-state.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["database_path"] = str(database)
        marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertEqual(1, cp.returncode)
        self.assertIn("store_import_state: contains unsupported fields", cp.stderr)
        self.assertNotIn(str(database), cp.stderr)
        self.assertNotIn("private-store.sqlite", cp.stderr)


if __name__ == "__main__":
    unittest.main()
