from __future__ import annotations

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403


class MetricsWorkflowTests(CliWorkflowTestCase):
    def test_gra_metrics_generates_advanced_workflow_counts_without_evidence(self) -> None:
        run_dir = self.copy_fixture_run("advanced-workflow-run")
        self.copy_advanced_workflow_outputs(run_dir)
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"][0]["evidence"] = "SHOULD_NOT_COPY_EVIDENCE_109"
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")
        traces = {
            "run_id": "advanced-workflow-run",
            "repo": "example/advanced-workflow",
            "branch": "main",
            "commit": "1111111111111111111111111111111111111111",
            "generated_at": "2026-05-28T00:00:00Z",
            "traces": [
                {
                    "id": "TRACE-101",
                    "finding_id": "SEC-101",
                    "producer_repo": "example/advanced-workflow",
                    "consumer_repo": "example/consumer-api",
                    "entry_points": ["repo/routes/upload.py"],
                    "sink": "src.report.render_report",
                    "attacker_control": "Probable",
                    "reachable": "Potential",
                    "evidence": "SHOULD_NOT_COPY_TRACE_EVIDENCE_109",
                    "limitations": ["static fixture only"],
                    "status": "Needs human review",
                }
            ],
        }
        (run_dir / "reports" / "traces.json").write_text(json.dumps(traces, indent=2) + "\n", encoding="utf-8")
        issue_plan = {
            "selected_findings": [
                {
                    "id": "SEC-101",
                    "advanced_validation": {
                        "warnings": ["needs human review before publication"],
                        "adversarial_validation": {"warnings": ["chain validation not final"]},
                    },
                }
            ]
        }
        (run_dir / "reports" / "issue-publication-plan.json").write_text(
            json.dumps(issue_plan, indent=2) + "\n",
            encoding="utf-8",
        )

        cp_gapfill = self.run_cmd([REPO_ROOT / "bin" / "gra-gapfill", "--run", run_dir, "--generate"], check=True)
        self.assertIn("Generated or reused 3 gapfill target(s)", cp_gapfill.stdout)
        command_events = run_dir / "reports" / "command-events.jsonl"
        with command_events.open("a", encoding="utf-8") as handle:
            for event in [
                {
                    "schema_version": "1",
                    "run_id": "advanced-workflow-run",
                    "repo": "example/advanced-workflow",
                    "command": "gra-research",
                    "phase": "exec",
                    "target_id": "TGT-101",
                    "started_at": "2026-05-28T00:00:00Z",
                    "ended_at": "2026-05-28T00:00:05Z",
                    "duration_ms": 5000,
                    "exit_code": 0,
                    "model": "gpt-5.5",
                    "effort": "xhigh",
                    "artifact_paths": ["reports/target-research/TGT-101.md"],
                    "source": "genai-repo-auditor",
                },
                {
                    "schema_version": "1",
                    "run_id": "advanced-workflow-run",
                    "repo": "example/advanced-workflow",
                    "command": "gra-research",
                    "phase": "exec",
                    "target_id": "TGT-101",
                    "started_at": "2026-05-28T00:01:00Z",
                    "ended_at": "2026-05-28T00:01:09Z",
                    "duration_ms": 9000,
                    "exit_code": 42,
                    "model": "gpt-5.5",
                    "effort": "xhigh",
                    "artifact_paths": ["codex-research-TGT-101-final.md"],
                    "source": "genai-repo-auditor",
                },
                {
                    "schema_version": "1",
                    "run_id": "advanced-workflow-run",
                    "repo": "example/advanced-workflow",
                    "command": "gra-validate-report",
                    "phase": "validate",
                    "target_id": None,
                    "started_at": "2026-05-28T00:02:00Z",
                    "ended_at": "2026-05-28T00:02:01Z",
                    "duration_ms": 1000,
                    "exit_code": 1,
                    "model": None,
                    "effort": None,
                    "artifact_paths": ["reports/findings.json"],
                    "source": "genai-repo-auditor",
                },
                {
                    "schema_version": "1",
                    "run_id": "advanced-workflow-run",
                    "repo": "example/advanced-workflow",
                    "command": "gra-validate-report",
                    "phase": "validate",
                    "target_id": None,
                    "started_at": "2026-05-28T00:03:00Z",
                    "ended_at": "2026-05-28T00:03:01Z",
                    "duration_ms": 1000,
                    "exit_code": 0,
                    "model": None,
                    "effort": None,
                    "artifact_paths": ["reports/findings.json"],
                    "source": "genai-repo-auditor",
                },
            ]:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
        taxonomy_log = run_dir / "reports" / "taxonomy-normalizations.jsonl"
        taxonomy_log.write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-28T00:04:00Z",
                    "source": "gra-taxonomy-preflight",
                    "artifact": str(run_dir / "reports" / "targets.json"),
                    "field_path": "targets.targets[0].taxonomies[0]",
                    "before": {"name": "CWE", "id": "CWE-284", "label": "Improper Access Control"},
                    "after": {"name": "CWE Subset", "id": "CWE-862", "label": "Missing Authorization"},
                    "reason": "alias",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        cp_metrics = self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        self.assertIn("Wrote", cp_metrics.stdout)
        self.assertIn("Findings: 3", cp_metrics.stdout)
        self.assertIn("Adversarial validations: 2", cp_metrics.stdout)
        self.assertIn("Chains: 1", cp_metrics.stdout)
        self.assertIn("Proofs: 2", cp_metrics.stdout)
        self.assertIn("Traces: 1", cp_metrics.stdout)
        self.assertIn("Gapfill current candidates: 3", cp_metrics.stdout)
        self.assertIn("Gapfill cumulative targets: 3", cp_metrics.stdout)
        self.assertIn("Command events: 5", cp_metrics.stdout)
        self.assertIn("Validation retries: 1", cp_metrics.stdout)
        self.assertIn("Taxonomy normalizations: 1", cp_metrics.stdout)
        self.assertIn("Latest status artifacts:", cp_metrics.stdout)
        self.assertIn("Archive artifacts:", cp_metrics.stdout)
        self.assertIn("Manifest hygiene warnings:", cp_metrics.stdout)

        metrics_text = (run_dir / "reports" / "metrics.json").read_text(encoding="utf-8")
        metrics_md = (run_dir / "reports" / "METRICS.md").read_text(encoding="utf-8")
        for forbidden in [
            "SHOULD_NOT_COPY_EVIDENCE_109",
            "SHOULD_NOT_COPY_TRACE_EVIDENCE_109",
            "Synthetic fixture code shows direct local data flow",
            "Static local trace shows token forwarding path",
        ]:
            self.assertNotIn(forbidden, metrics_text)
            self.assertNotIn(forbidden, metrics_md)
        self.assertIn("## Traces", metrics_md)
        self.assertIn("Trace attacker control", metrics_md)

        metrics = json.loads(metrics_text)
        self.assertEqual("local-report-artifacts", metrics["source"])
        self.assertTrue(metrics["safety"]["local_artifacts_only"])
        self.assertFalse(metrics["safety"]["raw_evidence_copied"])
        self.assertFalse(metrics["safety"]["secrets_copied"])
        self.assertEqual(3, metrics["findings"]["total"])
        self.assertEqual(1, metrics["findings"]["by_severity"]["Critical"])
        self.assertEqual(2, metrics["findings"]["issue_recommended"])
        self.assertEqual(1, metrics["adversarial_validation"]["by_decision"]["downgrade"])
        self.assertEqual(0.5, metrics["adversarial_validation"]["downgrade_or_invalidate_rate"])
        self.assertEqual(1, metrics["chains"]["total"])
        self.assertEqual(2, metrics["proofs"]["total"])
        self.assertEqual(2, metrics["gapfill"]["source_targets_recommended"])
        self.assertEqual(3, metrics["gapfill"]["current_run"]["candidate_count"])
        self.assertEqual(3, metrics["gapfill"]["current_run"]["generated_target_count"])
        self.assertEqual(3, metrics["gapfill"]["cumulative"]["generated_target_count"])
        self.assertEqual(3, metrics["gapfill"]["targets_generated"])
        self.assertEqual(1, metrics["traces"]["total"])
        self.assertEqual(2, metrics["issue_publication_plan"]["warning_count"])
        self.assertEqual(5, metrics["observability"]["total_events"])
        self.assertEqual(1, metrics["observability"]["failures_by_target"]["TGT-101"])
        self.assertEqual(1, metrics["observability"]["failures_by_target"]["__run__"])
        self.assertEqual(1, metrics["observability"]["reruns_by_target"]["TGT-101"])
        self.assertEqual(1, metrics["observability"]["validation_retry_count"])
        self.assertEqual(1, metrics["observability"]["validation_retries_by_target"]["__run__"])
        self.assertEqual(1, metrics["observability"]["taxonomy_normalization_count"])
        self.assertEqual(1, metrics["observability"]["taxonomy_normalizations_by_target"]["TGT-101"])
        self.assertEqual("TGT-101", metrics["observability"]["execution_durations"][0]["target_id"])
        self.assertEqual(9000, metrics["observability"]["execution_durations"][0]["duration_ms"])
        self.assertGreater(metrics["artifacts"]["reports_file_count"], 0)
        self.assertIn("manifest_by_retention", metrics["artifacts"])
        self.assertIn("latest_status_artifact_count", metrics["artifacts"])
        self.assertIn("archive_artifact_count", metrics["artifacts"])
        self.assertIn("manifest_hygiene_warnings", metrics["artifacts"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Metrics: validated", cp_validate.stdout)
        self.assertIn("Command events: validated", cp_validate.stdout)

        cp_dashboard = self.run_cmd([REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir], check=True)
        self.assertIn("dashboard.html", cp_dashboard.stdout)
        dashboard = (run_dir / "reports" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Advanced workflow metrics", dashboard)
        self.assertIn("metrics.json", dashboard)
        self.assertIn("METRICS.md", dashboard)
        self.assertIn("Downgrade/invalidate rate", dashboard)
        self.assertIn("Long-running target executions", dashboard)
        self.assertIn("High retry / rerun targets", dashboard)
        self.assertIn("Taxonomy normalizations", dashboard)
        self.assertIn("TGT-101", dashboard)
        self.assertIn("Gapfill current and cumulative queue", dashboard)
        self.assertIn("Current source-to-gapfill relationships", dashboard)
        self.assertIn("Next gapfill targets", dashboard)
        self.assertIn("Artifact retention", dashboard)
        self.assertIn("Latest status artifacts", dashboard)
        self.assertIn("Archive artifacts", dashboard)

    def test_gra_benchmark_fixture_advanced_runs_without_network_or_raw_evidence(self) -> None:
        out_run = self.work_dir / "advanced-benchmark"
        gh_log = self.work_dir / "benchmark-gh-calls.jsonl"
        codex_log = self.work_dir / "benchmark-codex-calls.jsonl"
        env = self.env.copy()
        env["GRA_MOCK_GH_LOG"] = str(gh_log)
        env["GRA_MOCK_CODEX_LOG"] = str(codex_log)

        cp = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-benchmark", "--fixture", "advanced", "--out-run", out_run],
            env=env,
            check=True,
        )
        self.assertIn("Overall status: passed", cp.stdout)
        self.assertIn("Metrics source: computed-fallback", cp.stdout)
        self.assertIn("Adversarial downgrade/invalidate rate: 0.5000", cp.stdout)
        self.assertFalse(gh_log.exists(), "benchmark fixture path must not call gh")
        self.assertFalse(codex_log.exists(), "benchmark fixture path must not call codex")

        benchmark_json = out_run / "reports" / "benchmark.json"
        benchmark_md = out_run / "reports" / "BENCHMARK.md"
        self.assertTrue(benchmark_json.exists())
        self.assertTrue(benchmark_md.exists())
        benchmark_text = benchmark_json.read_text(encoding="utf-8")
        benchmark_md_text = benchmark_md.read_text(encoding="utf-8")
        for forbidden in [
            "Synthetic fixture code shows direct local data flow",
            "Static local trace shows token forwarding path",
            "Fixture handler passes request-controlled body",
        ]:
            self.assertNotIn(forbidden, benchmark_text)
            self.assertNotIn(forbidden, benchmark_md_text)

        benchmark = json.loads(benchmark_text)
        self.assertEqual("local-benchmark", benchmark["source"])
        self.assertEqual("advanced", benchmark["fixture"]["name"])
        self.assertFalse(benchmark["safety"]["network_accessed"])
        self.assertFalse(benchmark["safety"]["issue_apply_performed"])
        self.assertEqual("computed-fallback", benchmark["metrics"]["source"])
        self.assertEqual(3, benchmark["metrics"]["summary"]["findings_total"])
        self.assertEqual(1, benchmark["metrics"]["summary"]["chain_count"])
        self.assertEqual(0.5, benchmark["metrics"]["summary"]["adversarial_downgrade_or_invalidate_rate"])
        gates = {item["id"]: item for item in benchmark["quality_gates"]}
        self.assertEqual("pass", gates["report-validation"]["status"])
        self.assertEqual("pass", gates["secret-scan"]["status"])
        self.assertEqual("pass", gates["no-public-issue-apply"]["status"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", out_run], check=True)
        self.assertIn("Benchmark: validated", cp_validate.stdout)

        cp_dashboard = self.run_cmd([REPO_ROOT / "bin" / "gra-dashboard", "--run", out_run], check=True)
        self.assertIn("dashboard.html", cp_dashboard.stdout)
        dashboard = (out_run / "reports" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Dogfood benchmark", dashboard)
        self.assertIn("benchmark.json", dashboard)
        self.assertIn("BENCHMARK.md", dashboard)

    def test_gra_benchmark_uses_existing_metrics_when_present(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-benchmark", "--run", run_dir], check=True)
        self.assertIn("Metrics source: metrics.json", cp.stdout)
        benchmark = json.loads((run_dir / "reports" / "benchmark.json").read_text(encoding="utf-8"))
        self.assertTrue(benchmark["metrics"]["artifact_present"])
        self.assertFalse(benchmark["metrics"]["degraded"])
        self.assertEqual("metrics.json", benchmark["metrics"]["source"])
        self.assertEqual(1, benchmark["metrics"]["summary"]["findings_total"])

    def test_gra_benchmark_rejects_missing_context_without_creating_reports(self) -> None:
        missing_run = self.work_dir / "missing-run"
        cp_missing = self.run_cmd([REPO_ROOT / "bin" / "gra-benchmark", "--run", missing_run])
        self.assertEqual(2, cp_missing.returncode)
        self.assertIn("benchmark run directory not found", cp_missing.stderr)
        self.assertFalse(missing_run.exists())

        bad_run = self.work_dir / "bad-run"
        bad_run.mkdir()
        cp_bad = self.run_cmd([REPO_ROOT / "bin" / "gra-benchmark", "--run", bad_run])
        self.assertEqual(2, cp_bad.returncode)
        self.assertIn("benchmark run context not found", cp_bad.stderr)
        self.assertFalse((bad_run / "reports").exists())

    def test_gra_benchmark_treats_null_context_fields_as_defaults(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["run_id"] = None
        context["repo"] = None
        context["branch"] = None
        context["commit"] = None
        context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")

        self.run_cmd([REPO_ROOT / "bin" / "gra-benchmark", "--run", run_dir], check=True)
        benchmark = json.loads((run_dir / "reports" / "benchmark.json").read_text(encoding="utf-8"))
        self.assertEqual(run_dir.name, benchmark["run_id"])
        self.assertEqual("", benchmark["repo"])
        self.assertEqual("", benchmark["branch"])
        self.assertEqual("", benchmark["commit"])
        self.assertNotEqual("None", benchmark["run_id"])
        self.assertNotEqual("None", benchmark["repo"])

    def test_gra_benchmark_fails_secret_gate_without_copying_secret_value(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        probe_value = synthetic_probe("ghp_", "A" * 24)
        (run_dir / "reports" / "generated-secret.txt").write_text(
            f"example=REDACTED\nreal-token={probe_value}\n",
            encoding="utf-8",
        )

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-benchmark", "--run", run_dir])
        self.assertEqual(1, cp.returncode, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertIn("Overall status: failed", cp.stdout)
        self.assertNotIn(probe_value, cp.stdout)
        self.assertNotIn(probe_value, cp.stderr)

        benchmark_text = (run_dir / "reports" / "benchmark.json").read_text(encoding="utf-8")
        benchmark_md = (run_dir / "reports" / "BENCHMARK.md").read_text(encoding="utf-8")
        self.assertNotIn(probe_value, benchmark_text)
        self.assertNotIn(probe_value, benchmark_md)
        benchmark = json.loads(benchmark_text)
        gates = {item["id"]: item for item in benchmark["quality_gates"]}
        self.assertEqual("fail", gates["secret-scan"]["status"])
        self.assertEqual(1, gates["secret-scan"]["value"])
        self.assertEqual(["reports/generated-secret.txt"], gates["secret-scan"]["artifact_paths"])

    def test_gra_evidence_graph_links_advanced_artifacts_without_raw_payloads(self) -> None:
        run_dir = self.copy_fixture_run("advanced-workflow-run")
        self.copy_advanced_workflow_outputs(run_dir)
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"][0]["evidence"] = "SHOULD_NOT_COPY_EVIDENCE_GRAPH_FINDING"
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

        traces = {
            "run_id": "advanced-workflow-run",
            "repo": "example/advanced-workflow",
            "branch": "main",
            "commit": "1111111111111111111111111111111111111111",
            "generated_at": "2026-05-28T00:00:00Z",
            "traces": [
                {
                    "id": "TRACE-101",
                    "finding_id": "SEC-101",
                    "producer_repo": "example/advanced-workflow",
                    "consumer_repo": "example/consumer-api",
                    "entry_points": ["repo/routes/upload.py"],
                    "sink": "src.report.render_report",
                    "attacker_control": "Probable",
                    "reachable": "Potential",
                    "evidence": "SHOULD_NOT_COPY_EVIDENCE_GRAPH_TRACE",
                    "limitations": ["static fixture only"],
                    "status": "Needs human review",
                }
            ],
        }
        (run_dir / "reports" / "traces.json").write_text(json.dumps(traces, indent=2) + "\n", encoding="utf-8")

        remediation_root = run_dir / "reports" / "remediation"
        patch_root = remediation_root / "SEC-101"
        patch_root.mkdir(parents=True, exist_ok=True)
        (patch_root / "patch.diff").write_text(
            "diff --git a/repo/src/handler.py b/repo/src/handler.py\n"
            "--- a/repo/src/handler.py\n"
            "+++ b/repo/src/handler.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-old\n"
            "+new\n",
            encoding="utf-8",
        )
        (patch_root / "notes.md").write_text("Local draft notes only.\n", encoding="utf-8")
        (patch_root / "subject.json").write_text(json.dumps({"finding_id": "SEC-101"}) + "\n", encoding="utf-8")
        remediation_candidates = {
            "schema_version": "1",
            "run_id": "advanced-workflow-run",
            "repo": "example/advanced-workflow",
            "branch": "main",
            "commit": "1111111111111111111111111111111111111111",
            "generated_at": "2026-05-28T00:00:01Z",
            "candidates": [
                {
                    "id": "PATCH-101",
                    "finding_id": "SEC-101",
                    "status": "draft",
                    "safe_by_design": True,
                    "patch_file": "reports/remediation/SEC-101/patch.diff",
                    "notes_file": "reports/remediation/SEC-101/notes.md",
                    "subject_file": "reports/remediation/SEC-101/subject.json",
                    "summary": "SHOULD_NOT_COPY_EVIDENCE_GRAPH_REMEDIATION_TEXT",
                    "files_touched": ["repo/src/handler.py"],
                    "expected_validation": ["python parser check"],
                    "limitations": ["fixture only"],
                    "requires_human_review": True,
                }
            ],
        }
        (remediation_root / "remediation-candidates.json").write_text(
            json.dumps(remediation_candidates, indent=2) + "\n",
            encoding="utf-8",
        )
        patch_validation = {
            "schema_version": "1",
            "run_id": "advanced-workflow-run",
            "repo": "example/advanced-workflow",
            "branch": "main",
            "commit": "1111111111111111111111111111111111111111",
            "generated_at": "2026-05-28T00:00:02Z",
            "patch_id": "PATCH-101",
            "finding_id": "SEC-101",
            "sandbox_profile": "local-test",
            "network_allowed": False,
            "patch_file": "reports/remediation/SEC-101/patch.diff",
            "candidate_file": "reports/remediation/remediation-candidates.json",
            "validation_workspace": {"path": "reports/remediation/SEC-101/.validation-workspace", "disposed": True},
            "patch_applied": False,
            "build_status": "not-run",
            "test_status": "not-run",
            "safe_proof_replay_status": "not-run",
            "adversarial_review_status": "needs-human-review",
            "diff_scope_status": "needs-human-review",
            "final_status": "needs-human-review",
            "checks": [],
            "commands_run": [],
            "limitations": ["no local commands configured"],
        }
        (patch_root / "patch-validation.json").write_text(
            json.dumps(patch_validation, indent=2) + "\n",
            encoding="utf-8",
        )

        cp_plan = self.run_cmd([REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--plan"], check=True)
        self.assertIn("Wrote issue publication plan:", cp_plan.stdout)
        self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)

        cp_graph = self.run_cmd([REPO_ROOT / "bin" / "gra-evidence-graph", "--run", run_dir], check=True)
        self.assertIn("Evidence graph JSON:", cp_graph.stdout)
        self.assertIn("Nodes:", cp_graph.stdout)
        graph_text = (run_dir / "reports" / "evidence-graph.json").read_text(encoding="utf-8")
        graph_md = (run_dir / "reports" / "EVIDENCE_GRAPH.md").read_text(encoding="utf-8")
        for forbidden in [
            "SHOULD_NOT_COPY_EVIDENCE_GRAPH_FINDING",
            "SHOULD_NOT_COPY_EVIDENCE_GRAPH_TRACE",
            "SHOULD_NOT_COPY_EVIDENCE_GRAPH_REMEDIATION_TEXT",
        ]:
            self.assertNotIn(forbidden, graph_text)
            self.assertNotIn(forbidden, graph_md)

        graph = json.loads(graph_text)
        node_types = {node["type"] for node in graph["nodes"]}
        self.assertTrue(
            {
                "finding",
                "target",
                "scanner_lead",
                "chain",
                "proof",
                "validation",
                "trace",
                "remediation_candidate",
                "patch_validation",
                "issue_plan_entry",
                "metric",
            }.issubset(node_types),
            node_types,
        )
        edge_types = {edge["type"] for edge in graph["edges"]}
        self.assertTrue({"supports", "challenges", "validated_by", "depends_on", "publication_candidate"}.issubset(edge_types), edge_types)
        self.assertEqual(2, graph["summary"]["high_critical_issue_recommended_findings"])
        self.assertEqual(2, graph["summary"]["high_critical_with_supporting_evidence"])
        self.assertEqual(2, graph["summary"]["high_critical_with_challenging_evidence"])
        self.assertEqual([], graph["summary"]["missing_optional_artifacts"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Evidence graph: validated", cp_validate.stdout)
        self.assertIn("Patch validations: validated", cp_validate.stdout)

        cp_dashboard = self.run_cmd([REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir], check=True)
        self.assertIn("dashboard.html", cp_dashboard.stdout)
        dashboard = (run_dir / "reports" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Evidence graph", dashboard)
        self.assertIn("evidence-graph.json", dashboard)
        self.assertIn("EVIDENCE_GRAPH.md", dashboard)
        self.assertIn("With supporting evidence", dashboard)

    def test_gra_evidence_graph_rejects_reports_dir_path_traversal(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        ctx_path = run_dir / "context.json"
        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        ctx["reports_dir"] = "../outside-reports"
        ctx_path.write_text(json.dumps(ctx, indent=2) + "\n", encoding="utf-8")

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-evidence-graph", "--run", run_dir])

        self.assertEqual(2, cp.returncode)
        self.assertIn("reports_dir must not contain path traversal", cp.stderr)
        self.assertFalse((self.work_dir / "outside-reports").exists())

    def test_gra_evidence_graph_skips_symlinked_patch_validation_dirs(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        remediation_root = run_dir / "reports" / "remediation"
        remediation_root.mkdir(parents=True, exist_ok=True)
        external_dir = self.work_dir / "external-remediation"
        external_dir.mkdir()
        (external_dir / "patch-validation.json").write_text(
            json.dumps(
                {
                    "patch_id": "PATCH-EXTERNAL",
                    "final_status": "needs-human-review",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (remediation_root / "external-ref").symlink_to(external_dir, target_is_directory=True)

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-evidence-graph", "--run", run_dir], check=True)

        self.assertIn("Evidence graph JSON:", cp.stdout)
        graph_text = (run_dir / "reports" / "evidence-graph.json").read_text(encoding="utf-8")
        graph = json.loads(graph_text)
        self.assertNotIn("PATCH-EXTERNAL", graph_text)
        self.assertNotIn(str(external_dir), graph_text)
        self.assertFalse(any(node["type"] == "patch_validation" for node in graph["nodes"]))

    def test_gra_metrics_handles_missing_optional_artifacts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        self.assertIn("Findings: 1", cp.stdout)
        metrics = json.loads((run_dir / "reports" / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(1, metrics["findings"]["total"])
        self.assertTrue(metrics["summary"]["public_safe"])
        self.assertEqual(1, metrics["summary"]["findings_total"])
        self.assertEqual(1, metrics["summary"]["issue_recommended_findings"])
        self.assertEqual(0, metrics["summary"]["issue_publication_warning_count"])
        self.assertEqual(0, metrics["summary"]["benchmark"]["gate_count"])
        self.assertFalse(metrics["summary"]["benchmark"]["artifact_present"])
        self.assertFalse(metrics["summary"]["scanner"]["artifact_present"])
        self.assertFalse(metrics["adversarial_validation"]["artifact_present"])
        self.assertFalse(metrics["chains"]["artifact_present"])
        self.assertFalse(metrics["proofs"]["artifact_present"])
        self.assertFalse(metrics["traces"]["artifact_present"])
        self.assertFalse(metrics["issue_publication_plan"]["artifact_present"])
        self.assertEqual(0, metrics["adversarial_validation"]["downgrade_or_invalidate_rate"])
        self.assertIn("Run duration was not available", (run_dir / "reports" / "METRICS.md").read_text(encoding="utf-8"))

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Metrics: validated", cp_validate.stdout)

    def test_gra_metrics_skips_symlinked_report_directories(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        outside = self.work_dir / "outside-reports"
        outside.mkdir()
        (outside / "outside-secret.txt").write_text("do not count me\n", encoding="utf-8")
        (run_dir / "reports" / "linked-outside").symlink_to(outside, target_is_directory=True)

        self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        metrics = json.loads((run_dir / "reports" / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(3, metrics["artifacts"]["reports_file_count"])
        self.assertEqual(1, metrics["artifacts"]["reports_dir_count"])

    def test_gra_metrics_buckets_unexpected_dimension_values(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        secret = "SHOULD_NOT_COPY_SECRET_DIMENSION_109"

        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"][0]["severity"] = secret
        findings["findings"][0]["status"] = secret
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

        targets_path = run_dir / "reports" / "targets.json"
        targets = json.loads(targets_path.read_text(encoding="utf-8"))
        targets["targets"].append(
            {
                "id": "TGT-GAPFILL-109",
                "category": "gapfill",
                "title": "Synthetic gapfill target",
                "risk": "medium",
                "priority": 20,
                "status": secret,
                "scope": "app.py",
                "entry_points": [],
                "trust_boundaries": [],
                "sinks": [],
                "review_questions": [],
                "recommended_mode": "exec",
            }
        )
        targets_path.write_text(json.dumps(targets, indent=2) + "\n", encoding="utf-8")

        (run_dir / "reports" / "validation.json").write_text(
            json.dumps({"validations": [{"decision": secret}]}, indent=2) + "\n",
            encoding="utf-8",
        )
        (run_dir / "reports" / "proofs.json").write_text(
            json.dumps({"proofs": [{"proof_type": secret, "status": secret}]}, indent=2) + "\n",
            encoding="utf-8",
        )
        (run_dir / "reports" / "chains.json").write_text(
            json.dumps({"chains": [{"severity": secret, "status": secret}]}, indent=2) + "\n",
            encoding="utf-8",
        )
        (run_dir / "reports" / "traces.json").write_text(
            json.dumps(
                {
                    "traces": [
                        {
                            "reachable": secret,
                            "attacker_control": secret,
                            "status": secret,
                        }
                    ]
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (run_dir / "run-manifest.json").write_text(
            json.dumps(
                {
                    "artifacts": [{"path": "reports/findings.json", "kind": secret, "retention": secret}],
                    "artifact_retention": {
                        "latest_status_artifacts": secret,
                        "archive_artifacts": secret,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        metrics_text = (run_dir / "reports" / "metrics.json").read_text(encoding="utf-8")
        metrics_md = (run_dir / "reports" / "METRICS.md").read_text(encoding="utf-8")
        self.assertNotIn(secret, metrics_text)
        self.assertNotIn(secret, metrics_md)

        metrics = json.loads(metrics_text)
        self.assertEqual(1, metrics["findings"]["by_severity"]["Unknown"])
        self.assertEqual(1, metrics["findings"]["by_status"]["Unknown"])
        self.assertEqual(1, metrics["adversarial_validation"]["by_decision"]["unknown"])
        self.assertEqual(1, metrics["proofs"]["by_type"]["unknown"])
        self.assertEqual(1, metrics["gapfill"]["targets_by_status"]["unknown"])
        self.assertEqual(1, metrics["traces"]["by_reachable"]["Not assessed"])
        self.assertEqual(1, metrics["artifacts"]["manifest_by_kind"]["unknown"])
        self.assertEqual(1, metrics["artifacts"]["manifest_by_retention"]["unknown"])
        self.assertEqual(0, metrics["artifacts"]["latest_status_artifact_count"])
        self.assertEqual(0, metrics["artifacts"]["archive_artifact_count"])
        self.assertEqual(3, metrics["artifacts"]["manifest_hygiene_warnings"])

    def test_gra_metrics_counts_manifest_retention_summary_mismatches(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "run-manifest.json").write_text(
            json.dumps(
                {
                    "artifacts": [{"path": "reports/findings.json", "kind": "file", "retention": "latest"}],
                    "artifact_retention": {
                        "latest_status_artifacts": [],
                        "supporting_artifacts": [],
                        "archive_artifacts": ["reports/findings.json"],
                        "by_retention": {"latest": 1, "supporting": 0, "archive": 0},
                        "notes": "fixture",
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        metrics = json.loads((run_dir / "reports" / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(0, metrics["artifacts"]["latest_status_artifact_count"])
        self.assertEqual(1, metrics["artifacts"]["archive_artifact_count"])
        self.assertEqual(2, metrics["artifacts"]["manifest_hygiene_warnings"])

    def test_gra_metrics_reports_issue_ledger_counts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        issue_url = "https://github.example.invalid/example/demo/issues/74"
        env, _log_path = self.env_with_gh_log(GRA_MOCK_ISSUE_URL=issue_url)
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            env=env,
            check=True,
        )

        self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        metrics = json.loads((run_dir / "reports" / "metrics.json").read_text(encoding="utf-8"))
        self.assertTrue(metrics["issue_ledger"]["artifact_present"])
        self.assertEqual(metrics["issue_ledger"]["tracked_findings"], 1)
        self.assertEqual(metrics["issue_ledger"]["published_findings"], 1)
        self.assertEqual(metrics["issue_ledger"]["by_publication_status"], {"published": 1})
        self.assertTrue(metrics["duplicate_decisions"]["artifact_present"])
        self.assertEqual(metrics["duplicate_decisions"]["total"], 1)
        self.assertEqual(metrics["duplicate_decisions"]["by_decision"], {"new": 1})
