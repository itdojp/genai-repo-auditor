from __future__ import annotations

import sqlite3

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403

from scanner_reporting import append_scanner_run, build_scanner_run_record  # noqa: E402


class ScannerStoreWorkflowTests(CliWorkflowTestCase):
    def test_metrics_and_evidence_graph_reject_noncanonical_scanner_run_refs(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "reports").rename(run_dir / "artifacts")
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "artifacts"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")
        scanner_results = run_dir / "artifacts" / "scanner-results"
        normalized = scanner_results / "normalized" / "gitleaks-leads.json"
        normalized.parent.mkdir(parents=True)
        normalized.write_text('{"leads": []}\n', encoding="utf-8")
        scanner_index = scanner_results / "scanner-index.json"
        scanner_index.write_text('{"results": []}\n', encoding="utf-8")
        record = build_scanner_run_record(
            adapter_id="gitleaks",
            tool_version="8.30.1",
            image="gitleaks@sha256:" + "a" * 64,
            status="succeeded",
            scanner_status="completed-no-leads",
            started_at="2026-07-11T00:00:00Z",
            ended_at="2026-07-11T00:00:01Z",
            duration_ms=1000,
            scanner_exit_code=0,
            result_count=0,
            normalized_leads_count=0,
            redaction_count=0,
            sandbox_profile="container",
            runtime="docker",
            network_accessed=False,
            result_classification="scanner-leads",
            normalized_result_ref="artifacts/scanner-results/normalized/gitleaks-leads.json",
            scanner_index_ref="artifacts/scanner-results/scanner-index.json",
        )
        report, report_path, _ = append_scanner_run(run_dir, record)
        report["runs"][0]["scanner_index_ref"] = "reports/scanner-results/scanner-index.json"
        report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

        for command in ("gra-evidence-graph", "gra-metrics"):
            cp = self.run_cmd([REPO_ROOT / "bin" / command, "--run", run_dir])
            self.assertEqual(2, cp.returncode, f"{command}: {cp.stdout}\n{cp.stderr}")
            self.assertIn("scanner-runs.json is not public-safe", cp.stderr)
            self.assertNotIn("Traceback", cp.stderr)

    def test_evidence_graph_rejects_malformed_scanner_runs_without_traceback(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        scanner_runs = run_dir / "reports" / "scanner-runs.json"
        scanner_runs.write_text("[]\n", encoding="utf-8")

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-evidence-graph", "--run", run_dir])

        self.assertEqual(2, cp.returncode)
        self.assertIn("scanner-runs.json is not public-safe", cp.stderr)
        self.assertNotIn("Traceback", cp.stderr)

    def test_reporting_failures_emit_events_after_successful_preflight(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        dashboard_out = run_dir / "reports" / "dashboard-output"
        sarif_out = run_dir / "reports" / "sarif-output"
        database_out = run_dir / "reports" / "database-output"
        for path in [dashboard_out, sarif_out, database_out]:
            path.mkdir()

        commands = [
            ([REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir, "--out", dashboard_out], "gra-dashboard", "dashboard"),
            ([REPO_ROOT / "bin" / "gra-sarif", "--run", run_dir, "--out", sarif_out], "gra-sarif", "sarif"),
            ([REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", database_out], "gra-store", "store"),
        ]
        for command, expected_command, expected_phase in commands:
            cp = self.run_cmd(command)
            self.assertEqual(2, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
            self.assertNotIn("Traceback", cp.stderr)
            event = self.read_command_events(run_dir)[-1]
            self.assert_public_command_event(
                event,
                command=expected_command,
                phase=expected_phase,
                exit_code=2,
                status="failed",
            )
            self.assertEqual("reporting_failure", event["error_category"])
            self.assertEqual([], event["output_artifact_refs"])

    def test_store_rejects_invalid_event_context_before_database_mutation(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["repo"] = "invalid repo with spaces"
        context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        database = self.work_dir / "must-not-exist.sqlite"

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", database])

        self.assertEqual(2, cp.returncode)
        self.assertIn("event.repo", cp.stderr)
        self.assertFalse(database.exists())
        self.assertFalse((run_dir / "reports" / "command-events.jsonl").exists())

    def test_ingest_and_import_events_respect_custom_reports_dir(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "reports").rename(run_dir / "custom-reports")
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "custom-reports"
        context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        scanner_file = self.work_dir / "custom-reports-scanner.json"
        scanner_file.write_text('{"results": []}\n', encoding="utf-8")

        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "semgrep", "--file", scanner_file],
            check=True,
        )
        external_file = self.work_dir / "custom-reports-external.json"
        external_file.write_text(json.dumps({"source": "fixture-import", "findings": []}) + "\n", encoding="utf-8")
        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-import-findings", "--run", run_dir, "--file", external_file],
            check=True,
        )
        self.run_cmd([REPO_ROOT / "bin" / "gra-scanner-triage", "--run", run_dir], check=True)

        events_path = run_dir / "custom-reports" / "command-events.jsonl"
        self.assertTrue(events_path.is_file())
        events = self.read_command_events(run_dir)
        self.assertEqual(
            ["gra-ingest", "gra-import-findings", "gra-scanner-triage"],
            [event["command"] for event in events],
        )
        self.assertIn("custom-reports/scanner-results/scanner-index.json", events[-1]["input_artifact_refs"])
        for event in events[:2]:
            self.assertTrue(all(ref == "context.json" or ref.startswith("custom-reports/") for ref in event["input_artifact_refs"] + event["output_artifact_refs"]))

    def test_ingest_scanner_triage_dashboard_sarif_and_store(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        scanner_file = self.work_dir / "semgrep.json"
        scanner_file.write_text('{"results": [{"check_id": "fixture.rule"}]}\n', encoding="utf-8")

        cp_ingest = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-ingest",
                "--run",
                run_dir,
                "--tool",
                "semgrep",
                "--file",
                scanner_file,
                "--format",
                "json",
                "--note",
                "fixture",
            ],
            check=True,
        )
        self.assertIn("Ingested", cp_ingest.stdout)
        index_path = run_dir / "reports" / "scanner-results" / "scanner-index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(index["results"][0]["tool"], "semgrep")
        normalized_path = run_dir / index["results"][0]["normalized_path"]
        self.assertTrue(normalized_path.exists())
        normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
        self.assertEqual(index["results"][0]["normalized_leads_count"], len(normalized["leads"]))
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events))
        self.assert_public_command_event(events[0], command="gra-ingest", phase="ingest", subject_id="semgrep")
        self.assertIn("context.json", events[0]["input_artifact_refs"])
        self.assertIn("reports/scanner-results/scanner-index.json", events[0]["output_artifact_refs"])
        self.assertIn(index["results"][0]["normalized_path"], events[0]["output_artifact_refs"])
        cp_metrics = self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        self.assertIn("metrics.json", cp_metrics.stdout)
        metrics = json.loads((run_dir / "reports" / "metrics.json").read_text(encoding="utf-8"))
        self.assertTrue(metrics["summary"]["scanner"]["artifact_present"])
        self.assertEqual(1, metrics["summary"]["scanner"]["result_count"])
        self.assertEqual(len(normalized["leads"]), metrics["summary"]["scanner"]["normalized_leads_count"])
        events = self.read_command_events(run_dir)
        self.assertEqual(2, len(events))
        self.assert_public_command_event(events[1], command="gra-metrics", phase="metrics")

        cp_triage = self.run_cmd([REPO_ROOT / "bin" / "gra-scanner-triage", "--run", run_dir], check=True)
        self.assertIn("Codex status: 0", cp_triage.stdout)
        triage_prompt = run_dir / "prompts" / "exec" / "scanner-triage.prompt.md"
        self.assertIn("reports/scanner-results/scanner-index.json", triage_prompt.read_text(encoding="utf-8"))
        self.assertIn("Normalized lead files", triage_prompt.read_text(encoding="utf-8"))
        events = self.read_command_events(run_dir)
        self.assertEqual(3, len(events))
        self.assert_public_command_event(events[2], command="gra-scanner-triage", phase="scanner-triage")
        self.assertEqual("gpt-5.5", events[2]["model"])
        self.assertEqual("xhigh", events[2]["effort"])
        self.assertFalse(events[2]["network_allowed"])
        self.assertIn("reports/scanner-results/scanner-index.json", events[2]["input_artifact_refs"])
        self.assertIn("prompts/exec/scanner-triage.prompt.md", events[2]["output_artifact_refs"])

        cp_dashboard = self.run_cmd([REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir], check=True)
        self.assertIn("dashboard.html", cp_dashboard.stdout)
        self.assertTrue((run_dir / "reports" / "dashboard.html").exists())

        cp_sarif = self.run_cmd([REPO_ROOT / "bin" / "gra-sarif", "--run", run_dir], check=True)
        self.assertIn("findings.sarif", cp_sarif.stdout)
        sarif = json.loads((run_dir / "reports" / "findings.sarif").read_text(encoding="utf-8"))
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertEqual(sarif["runs"][0]["results"][0]["ruleId"], "SEC-001")

        db_path = self.work_dir / "audit.sqlite"
        cp_store = self.run_cmd([REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", db_path], check=True)
        self.assertIn("Imported run", cp_store.stdout)
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("select count(*) from findings").fetchone()[0]
            posture_count = conn.execute("select count(*) from posture_artifacts").fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(posture_count, 0)
        events = self.read_command_events(run_dir)
        self.assertEqual(
            ["gra-ingest", "gra-metrics", "gra-scanner-triage", "gra-dashboard", "gra-sarif", "gra-store"],
            [event["command"] for event in events],
        )
        self.assert_public_command_event(events[3], command="gra-dashboard", phase="dashboard")
        self.assert_public_command_event(events[4], command="gra-sarif", phase="sarif")
        self.assert_public_command_event(events[5], command="gra-store", phase="store")
        self.assertNotIn(str(db_path), json.dumps(events[5]))

    def test_gra_store_and_index_persist_optional_posture_artifacts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.write_optional_posture_artifacts(run_dir)
        (run_dir / "reports" / "run-manifest.json").write_text(
            json.dumps({"schema_version": "1", "generated_at": "2026-05-24T00:00:05Z", "artifacts": []}) + "\n",
            encoding="utf-8",
        )

        db_path = self.work_dir / "posture.sqlite"
        self.run_cmd([REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", db_path], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", db_path], check=True)

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "select artifact_type, path, status, item_count, data_json "
                "from posture_artifacts order by artifact_type, path"
            ).fetchall()
        self.assertEqual(len(rows), 5)
        posture_by_type = {row[0]: row for row in rows}
        self.assertEqual(posture_by_type["run_manifest"][1], "run-manifest.json")
        self.assertEqual(posture_by_type["run_manifest"][3], 3)
        self.assertEqual(posture_by_type["agent_surface"][3], 2)
        self.assertEqual(posture_by_type["supply_chain_posture"][2], "needs_review")
        self.assertEqual(posture_by_type["supply_chain_posture"][3], 2)
        self.assertEqual(posture_by_type["provenance_posture"][2], "attested")
        self.assertEqual(posture_by_type["provenance_posture"][3], 1)
        self.assertEqual(posture_by_type["dependencies"][2], "vulnerabilities_observed")
        self.assertEqual(posture_by_type["dependencies"][3], 2)
        dependency_data = json.loads(posture_by_type["dependencies"][4])
        self.assertEqual(dependency_data["vulnerability_count"], 1)

        indexed_run = self.runs_dir / "example__demo" / "fixture-run"
        indexed_run.parent.mkdir(parents=True)
        shutil.copytree(run_dir, indexed_run)
        cp_index = self.run_cmd([REPO_ROOT / "bin" / "gra-index", "--runs-dir", self.runs_dir], check=True)
        self.assertIn("index.json", cp_index.stdout)

        index = json.loads((self.runs_dir / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(index["runs"]), 1)
        item = index["runs"][0]
        self.assertEqual(item["posture_artifact_count"], 5)
        self.assertEqual(item["agent_surface_count"], 2)
        self.assertEqual(item["scorecard_check_count"], 2)
        self.assertEqual(item["provenance_workflow_count"], 1)
        self.assertEqual(item["dependency_component_count"], 2)
        self.assertEqual(item["dependency_vulnerability_count"], 1)
        posture = item["posture"]
        self.assertEqual(posture["run_manifest_artifact_count"], 3)
        self.assertEqual(posture["statuses"]["dependencies"], "vulnerabilities_observed")
        self.assertEqual(posture["statuses"]["supply_chain_posture"], "needs_review")
        index_md = (self.runs_dir / "index.md").read_text(encoding="utf-8")
        self.assertIn("Posture artifacts", index_md)
        self.assertIn("Agent surfaces", index_md)
        self.assertIn("Vulnerabilities", index_md)

    def test_gra_store_skips_symlinked_posture_artifacts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        outside = self.work_dir / "outside-dependencies.json"
        outside.write_text(
            json.dumps(
                {
                    "schema_version": "1",
                    "status": "vulnerabilities_observed",
                    "component_count": 1,
                    "vulnerability_count": 0,
                    "components": [],
                    "vulnerabilities": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (run_dir / "reports" / "dependencies.json").symlink_to(outside)

        db_path = self.work_dir / "symlink-posture.sqlite"
        self.run_cmd([REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", db_path], check=True)
        with sqlite3.connect(db_path) as conn:
            posture_count = conn.execute("select count(*) from posture_artifacts").fetchone()[0]
        self.assertEqual(posture_count, 0)

    def test_gra_store_supports_report_run_manifest_path(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        reports = run_dir / "reports"
        (reports / "run-manifest.json").write_text(
            json.dumps({"schema_version": "1", "generated_at": "2026-05-24T00:00:00Z", "artifacts": []}) + "\n",
            encoding="utf-8",
        )
        db_path = self.work_dir / "manifest-fallback.sqlite"
        self.run_cmd([REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", db_path], check=True)
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "select artifact_type, path, status, item_count from posture_artifacts"
            ).fetchone()
        self.assertEqual(row, ("run_manifest", "reports/run-manifest.json", "present", 0))

    def test_gra_index_tolerates_malformed_context_when_summarizing_posture(self) -> None:
        indexed_run = self.runs_dir / "example__demo" / "fixture-run"
        indexed_run.parent.mkdir(parents=True)
        shutil.copytree(FIXTURES / "minimal-run", indexed_run)
        (indexed_run / "context.json").write_text("{not-json\n", encoding="utf-8")

        cp_index = self.run_cmd([REPO_ROOT / "bin" / "gra-index", "--runs-dir", self.runs_dir], check=True)
        self.assertIn("index.json", cp_index.stdout)
        index = json.loads((self.runs_dir / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(index["runs"]), 1)
        self.assertEqual(index["runs"][0]["run_id"], "fixture-run")
        self.assertEqual(index["runs"][0]["posture_artifact_count"], 0)

    def test_gra_ingest_normalizes_and_redacts_secret_scanner_outputs(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        stripe_probe = synthetic_probe("sk_live_", "1234567890abcdef")
        aws_probe = synthetic_probe("AKIA", "ABCDEFGHIJKLMNOP")
        gitleaks_file = self.work_dir / "gitleaks.json"
        gitleaks_file.write_text(
            json.dumps(
                [
                    {
                        "RuleID": "generic-api-key",
                        "Description": "Stripe key",
                        "File": "src/config.ts",
                        "StartLine": 42,
                        "Secret": stripe_probe,
                    }
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        trufflehog_file = self.work_dir / "trufflehog.json"
        trufflehog_file.write_text(
            json.dumps(
                {
                    "DetectorName": "AWS",
                    "Raw": aws_probe,
                    "SourceMetadata": {"Data": {"Git": {"file": "settings.py", "line": 7}}},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "gitleaks", "--file", gitleaks_file], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "trufflehog", "--file", trufflehog_file], check=True)

        index = json.loads((run_dir / "reports" / "scanner-results" / "scanner-index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(index["results"]), 2)
        index_text = json.dumps(index)
        self.assertNotIn(stripe_probe, index_text)
        self.assertNotIn(aws_probe, index_text)
        for entry in index["results"]:
            normalized_path = run_dir / entry["normalized_path"]
            normalized_text = normalized_path.read_text(encoding="utf-8")
            self.assertNotIn(stripe_probe, normalized_text)
            self.assertNotIn(aws_probe, normalized_text)
            normalized = json.loads(normalized_text)
            self.assertGreaterEqual(entry["normalized_leads_count"], 1)
            self.assertEqual(normalized["leads"][0]["raw_result_ref"], entry["path"])
        all_normalized = "\n".join((run_dir / entry["normalized_path"]).read_text(encoding="utf-8") for entry in index["results"])
        self.assertIn("sk_live_...cdef", all_normalized)
        self.assertIn("AKIA...MNOP", all_normalized)
        event_text = json.dumps(self.read_command_events(run_dir))
        self.assertNotIn(stripe_probe, event_text)
        self.assertNotIn(aws_probe, event_text)

    def test_ingestion_and_triage_failures_remain_nonzero_when_event_writes_warn(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        missing = self.work_dir / "missing-scanner.json"

        cp_ingest = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "semgrep", "--file", missing]
        )
        self.assertEqual(2, cp_ingest.returncode)
        ingest_event = self.read_command_events(run_dir)[0]
        self.assert_public_command_event(
            ingest_event,
            command="gra-ingest",
            phase="ingest",
            subject_id="semgrep",
            exit_code=2,
            status="failed",
        )
        self.assertEqual("input_validation", ingest_event["error_category"])

        events_path = run_dir / "reports" / "command-events.jsonl"
        events_path.unlink()
        events_path.symlink_to(self.work_dir / "outside-events.jsonl")
        cp_triage = self.run_cmd([REPO_ROOT / "bin" / "gra-scanner-triage", "--run", run_dir])
        self.assertEqual(2, cp_triage.returncode)
        self.assertIn("WARNING: command event was not written", cp_triage.stderr)

    def test_unsupported_dependency_shape_does_not_claim_unwritten_outputs(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        scanner_file = self.work_dir / "trivy-unsupported.json"
        scanner_file.write_text('{"unsupported": true}\n', encoding="utf-8")

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-ingest",
                "--run",
                run_dir,
                "--tool",
                "trivy",
                "--file",
                scanner_file,
                "--format",
                "json",
            ],
            check=True,
        )
        self.assertNotIn("dependencies.json", cp.stdout)
        self.assertFalse((run_dir / "reports" / "dependencies.json").exists())
        event = self.read_command_events(run_dir)[0]
        self.assertNotIn("reports/dependencies.json", event["output_artifact_refs"])
        self.assertNotIn("reports/DEPENDENCY_RISK.md", event["output_artifact_refs"])

    def test_gra_ingest_rejects_unsafe_reports_dir_before_copying_raw_output(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "../outside-reports"
        context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        scanner_file = self.work_dir / "scanner.json"
        scanner_file.write_text('{"results": []}\n', encoding="utf-8")

        cp = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "semgrep", "--file", scanner_file]
        )

        self.assertEqual(2, cp.returncode)
        self.assertIn("reports_dir must be a relative path under the run directory", cp.stderr)
        self.assertFalse((run_dir.parent / "outside-reports").exists())

    def test_gra_ingest_handles_generic_probe_large_json_and_sarif_locations(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        generic_probe = synthetic_probe("correct", "horse", "battery", "staple")
        aws_access_probe = synthetic_probe("wJalrXUtnFEMI/", "K7MDENG/bPxRfiCY", "1234567890")
        temp_aws_id = synthetic_probe("ASIA", "ABCDEFGHIJKLMNOP")
        generic_file = self.work_dir / "generic-secret.json"
        generic_file.write_text(json.dumps([{"RuleID": "generic-password", "File": "config.env", "StartLine": 3, "Raw": generic_probe}]) + "\n", encoding="utf-8")

        large_file = self.work_dir / "large-semgrep.json"
        large_file.write_text(
            json.dumps(
                {
                    "results": [
                        {"check_id": f"rule-{i}", "path": f"src/file{i}.py", "start": {"line": i + 1}, "extra": {"message": "x" * 25000}}
                        for i in range(3)
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        sarif_file = self.work_dir / "codeql.sarif"
        sarif_file.write_text(
            json.dumps(
                {
                    "runs": [
                        {
                            "results": [
                                {
                                    "ruleId": "py/test-rule",
                                    "level": "warning",
                                    "message": {"text": "example"},
                                    "locations": [
                                        {
                                            "physicalLocation": {
                                                "artifactLocation": {"uri": "src/main.py"},
                                                "region": {"startLine": 12},
                                            }
                                        }
                                    ],
                                }
                            ]
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        jsonl_file = self.work_dir / "trufflehog.jsonl"
        jsonl_file.write_text(
            "\n".join(
                [
                    json.dumps({"DetectorName": "generic", "Raw": generic_probe, "SourceMetadata": {"Data": {"Git": {"file": "a.env", "line": 1}}}}),
                    json.dumps({"DetectorName": "aws-secret", "Raw": aws_access_probe, "SourceMetadata": {"Data": {"Git": {"file": "b.env", "line": 2}}}}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        private_key_file = self.work_dir / "private-key.txt"
        private_key_file.write_text("-----BEGIN PRIVATE KEY-----\nABCDEF1234567890\n", encoding="utf-8")
        temp_aws_file = self.work_dir / "temp-aws.json"
        temp_aws_file.write_text(json.dumps([{"RuleID": "temp-aws", "File": "aws.env", "StartLine": 4, "Secret": temp_aws_id}]) + "\n", encoding="utf-8")

        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "custom", "--file", generic_file], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "semgrep", "--file", large_file], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "codeql", "--file", sarif_file, "--format", "sarif"], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "trufflehog", "--file", jsonl_file, "--format", "jsonl"], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "privatekey", "--file", private_key_file, "--format", "text"], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "gitleaks", "--file", temp_aws_file], check=True)

        index = json.loads((run_dir / "reports" / "scanner-results" / "scanner-index.json").read_text(encoding="utf-8"))
        by_tool = {entry["tool"]: json.loads((run_dir / entry["normalized_path"]).read_text(encoding="utf-8")) for entry in index["results"]}
        all_text = "\n".join(json.dumps(value) for value in by_tool.values())
        self.assertNotIn(generic_probe, all_text)
        self.assertNotIn(aws_access_probe, all_text)
        self.assertNotIn(temp_aws_id, all_text)
        self.assertNotIn("ABCDEF1234567890", all_text)
        self.assertIn("<REDACTED:scanner-secret>", all_text)
        self.assertIn("<REDACTED:private-key>", all_text)
        self.assertIn("ASIA...MNOP", all_text)
        self.assertEqual(len(by_tool["semgrep"]["leads"]), 3)
        self.assertEqual(by_tool["semgrep"]["leads"][0]["line"], 1)
        self.assertFalse(by_tool["semgrep"]["normalization"]["parse_error"])
        self.assertEqual(len(by_tool["trufflehog"]["leads"]), 2)
        sarif_lead = by_tool["codeql"]["leads"][0]
        self.assertEqual(sarif_lead["path"], "src/main.py")
        self.assertEqual(sarif_lead["line"], 12)

    def test_gra_import_findings_review_only_retains_rejected_and_redacts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        original_findings = json.loads((run_dir / "reports" / "findings.json").read_text(encoding="utf-8"))
        secret = "ghp_1234567890abcdefghijklmnop"
        external_file = self.work_dir / "external-findings.json"
        external_file.write_text(
            json.dumps(
                {
                    "source": "managed-ai-review",
                    "source_version": "2026.06",
                    "findings": [
                        {
                            "external_id": "EXT-001",
                            "title": f"Imported candidate containing {secret}",
                            "severity": "High",
                            "confidence": "Medium",
                            "status": "Potential",
                            "category": "sql-injection",
                            "affected_locations": [{"file": "app.py", "line": 2}],
                            "evidence": f"User input reaches SQL with token {secret}",
                            "minimal_remediation": "Use parameterized queries.",
                        },
                        {
                            "external_id": "EXT-001",
                            "title": f"Imported candidate containing {secret}",
                            "severity": "High",
                            "confidence": "Medium",
                            "status": "Potential",
                            "category": "sql-injection",
                            "affected_locations": [{"file": "app.py", "line": 2}],
                            "evidence": f"User input reaches SQL with token {secret}",
                            "minimal_remediation": "Use parameterized queries.",
                        },
                        {
                            "external_id": "EXT-BAD",
                            "title": "Invalid path candidate",
                            "severity": "Critical",
                            "confidence": "High",
                            "status": "Potential",
                            "category": "path-traversal",
                            "affected_locations": [{"file": "../secret.py", "line": 1}],
                            "evidence": "invalid path must be rejected",
                            "minimal_remediation": "Fix the path.",
                        },
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        cp_import = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-import-findings", "--run", run_dir, "--file", external_file],
            check=True,
        )
        self.assertIn("Review-only mode", cp_import.stdout)
        report_path = run_dir / "reports" / "imported-findings.json"
        self.assertTrue(report_path.exists())
        self.assertTrue((run_dir / "reports" / "IMPORTED_FINDINGS.md").exists())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "input_count": 3,
                "valid_count": 2,
                "rejected_count": 1,
                "appended_count": 0,
                "duplicate_skipped_count": 1,
            },
            report["summary"],
        )
        self.assertEqual("review-only", report["findings"][0]["append_status"])
        self.assertEqual("duplicate-skipped", report["findings"][1]["append_status"])
        self.assertEqual("EXT-BAD", report["rejected_findings"][0]["external_id"])
        self.assertIn("affected_locations[0].file", "; ".join(report["rejected_findings"][0]["reasons"]))
        self.assertNotIn(secret, json.dumps(report))
        import_events = self.read_command_events(run_dir)
        self.assertEqual(1, len(import_events))
        self.assert_public_command_event(
            import_events[0],
            command="gra-import-findings",
            phase="import",
            subject_id="managed-ai-review",
        )
        self.assertNotIn(secret, json.dumps(import_events))
        self.assertIn("reports/imported-findings.json", import_events[0]["output_artifact_refs"])
        self.assertEqual(
            original_findings["findings"],
            json.loads((run_dir / "reports" / "findings.json").read_text(encoding="utf-8"))["findings"],
        )

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Imported findings: validated", cp_validate.stdout)
        self.run_cmd([REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir], check=True)
        dashboard = (run_dir / "reports" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("External finding imports", dashboard)

    def test_gra_import_findings_append_mode_dedupes_and_keeps_publication_review_gated(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        external_file = self.work_dir / "external-append-findings.json"
        payload = {
            "source": "internal-review",
            "source_version": "1.2.3",
            "findings": [
                {
                    "external_id": "IR-001",
                    "title": "Imported SSRF candidate",
                    "severity": "Critical",
                    "confidence": "Medium",
                    "status": "Potential",
                    "category": "ssrf",
                    "affected_locations": [{"file": "app.py", "line": 3}],
                    "evidence": "URL parameter reaches an outbound request helper.",
                    "minimal_remediation": "Allowlist outbound destinations and validate schemes.",
                }
            ],
        }
        external_file.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        cp_first = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-import-findings",
                "--run",
                run_dir,
                "--file",
                external_file,
                "--append-findings",
            ],
            check=True,
        )
        self.assertIn("appended=1", cp_first.stdout)
        findings = json.loads((run_dir / "reports" / "findings.json").read_text(encoding="utf-8"))["findings"]
        self.assertEqual(2, len(findings))
        imported = findings[-1]
        self.assertTrue(str(imported["id"]).startswith("IMP-"))
        self.assertFalse(imported["issue_recommended"])
        self.assertEqual("internal-review", imported["external_source"]["source"])
        self.assertEqual("IR-001", imported["external_source"]["external_id"])

        cp_second = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-import-findings",
                "--run",
                run_dir,
                "--file",
                external_file,
                "--append-findings",
            ],
            check=True,
        )
        self.assertIn("duplicate_skipped=1", cp_second.stdout)
        deduped_findings = json.loads((run_dir / "reports" / "findings.json").read_text(encoding="utf-8"))["findings"]
        self.assertEqual(2, len(deduped_findings))
        report = json.loads((run_dir / "reports" / "imported-findings.json").read_text(encoding="utf-8"))
        self.assertEqual("duplicate-skipped", report["findings"][0]["append_status"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Imported findings: validated", cp_validate.stdout)
        cp_plan = self.run_cmd([REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--plan"], check=True)
        self.assertIn("Wrote issue publication plan:", cp_plan.stdout)
        plan = json.loads((run_dir / "reports" / "issue-publication-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(["SEC-001"], [item["id"] for item in plan["selected_findings"]])

    def test_gra_import_findings_rejects_broken_symlink_reports_dir(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        ctx_path = run_dir / "context.json"
        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        ctx["reports_dir"] = "broken-reports/reports"
        ctx_path.write_text(json.dumps(ctx, indent=2) + "\n", encoding="utf-8")
        (run_dir / "broken-reports").symlink_to(self.work_dir / "missing-target", target_is_directory=True)
        external_file = self.work_dir / "external-symlink-findings.json"
        external_file.write_text(
            json.dumps(
                {
                    "source": "internal-review",
                    "findings": [
                        {
                            "external_id": "IR-001",
                            "title": "Imported candidate",
                            "severity": "High",
                            "confidence": "Medium",
                            "status": "Potential",
                            "category": "input-validation",
                            "affected_locations": [{"file": "app.py", "line": 1}],
                            "evidence": "bounded evidence",
                            "minimal_remediation": "Validate input.",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-import-findings", "--run", run_dir, "--file", external_file])
        self.assertNotEqual(0, cp.returncode)
        self.assertIn("reports_dir must not contain symlink components", cp.stderr)
