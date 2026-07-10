from __future__ import annotations

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403


class WorkerProfileWorkflowTests(CliWorkflowTestCase):
    def test_gra_run_state_records_pause_resume_and_block_state(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        cp_pause = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-run-state",
                "--run",
                run_dir,
                "--pause",
                "--reason",
                "maintainer update window",
                "--resume-target",
                "TGT-AGENT-234",
                "--resume-condition",
                "main branch updated and post-merge CI passed",
                "--paused-by",
                "operator",
                "--final-reconcile",
                "published known findings: 52; unpublished Medium+: 0",
            ],
            check=True,
        )
        self.assertIn("Wrote run state", cp_pause.stdout)
        self.assertIn("Run state: paused", cp_pause.stdout)
        state_path = run_dir / "reports" / "run-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "paused")
        self.assertEqual(state["pause_reason"], "maintainer update window")
        self.assertEqual(state["resume_target"], "TGT-AGENT-234")
        self.assertEqual(state["paused_by"], "operator")

        cp_status = self.run_cmd([REPO_ROOT / "bin" / "gra-run-state", "--run", run_dir, "--status"], check=True)
        self.assertIn("Resume target: TGT-AGENT-234", cp_status.stdout)
        cp_resume = self.run_cmd([REPO_ROOT / "bin" / "gra-run-state", "--run", run_dir, "--resume"], check=True)
        self.assertIn("Pause reason: maintainer update window", cp_resume.stdout)
        self.assertIn("Previous final reconcile: published known findings: 52; unpublished Medium+: 0", cp_resume.stdout)
        self.assertIn("Resume target: TGT-AGENT-234", cp_resume.stdout)

        cp_valid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Run state: validated", cp_valid.stdout)

        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-run-state",
                "--run",
                run_dir,
                "--clear-pause",
                "--resumed-by",
                "operator",
            ],
            check=True,
        )
        active_state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(active_state["status"], "active")
        self.assertEqual(active_state["resumed_by"], "operator")

        cp_block = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-run-state",
                "--run",
                run_dir,
                "--block",
                "--reason",
                "external approval missing",
                "--blocked-by",
                "operator",
            ],
            check=True,
        )
        self.assertIn("Run state: blocked", cp_block.stdout)
        blocked_state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(blocked_state["status"], "blocked")
        self.assertEqual(blocked_state["block_reason"], "external approval missing")
        self.assertIsNone(blocked_state["pause_reason"])

    def test_paused_run_blocks_deep_review_and_allows_read_only_status(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-run-state",
                "--run",
                run_dir,
                "--pause",
                "--reason",
                "maintainer update window",
                "--resume-target",
                "TGT-001",
                "--final-reconcile",
                "findings 1; unpublished Medium+: 0",
            ],
            check=True,
        )

        status_cp = self.run_cmd([REPO_ROOT / "bin" / "gra-run-state", "--run", run_dir, "--status"], check=True)
        self.assertIn("Run state: paused", status_cp.stdout)
        list_cp = self.run_cmd([REPO_ROOT / "bin" / "gra-targets", "--run", run_dir, "--list"], check=True)
        self.assertIn("TGT-001", list_cp.stdout)
        gapfill_list_cp = self.run_cmd([REPO_ROOT / "bin" / "gra-gapfill", "--run", run_dir, "--list"], check=True)
        self.assertIn("No gapfill candidates", gapfill_list_cp.stdout)

        env, codex_log = self.env_with_codex_log()
        research_cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-research",
                "--run",
                run_dir,
                "--target",
                "TGT-001",
                "--mode",
                "exec",
            ],
            env=env,
        )
        self.assertEqual(research_cp.returncode, 5, research_cp.stderr)
        self.assertIn("Refusing to start target research for TGT-001", research_cp.stderr)
        self.assertIn("Resume target: TGT-001", research_cp.stderr)
        self.assertEqual(self.read_codex_calls(codex_log), [])
        self.assertEqual(self.target_by_id(run_dir, "TGT-001")["status"], "queued")
        self.assertFalse((run_dir / "reports" / "target-research" / "TGT-001.target.json").exists())

        generate_cp = self.run_cmd([REPO_ROOT / "bin" / "gra-gapfill", "--run", run_dir, "--generate"])
        self.assertEqual(generate_cp.returncode, 5, generate_cp.stderr)
        self.assertIn("Refusing to start gapfill generation or review", generate_cp.stderr)

        mark_cp = self.run_cmd([REPO_ROOT / "bin" / "gra-targets", "--run", run_dir, "--mark", "TGT-001", "reviewed"])
        self.assertEqual(mark_cp.returncode, 5, mark_cp.stderr)
        self.assertIn("Refusing to start target queue mutation or generation", mark_cp.stderr)

    def test_gra_no_findings_records_empty_findings_for_downstream_reporting(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        findings_path.unlink()

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-no-findings",
                "--run",
                run_dir,
                "--source-stage",
                "recon",
                "--reviewer",
                "test-operator",
                "--rationale",
                "Bounded reconnaissance completed and no candidate findings were advanced.",
            ],
            check=True,
        )

        self.assertIn("Findings: 0", cp.stdout)
        self.assertTrue(findings_path.exists())
        no_findings_md = run_dir / "reports" / "NO_FINDINGS.md"
        self.assertTrue(no_findings_md.exists())
        report = json.loads(findings_path.read_text(encoding="utf-8"))
        self.assertEqual([], report["findings"])
        self.assertEqual("no-confirmed-findings", report["no_findings"]["status"])
        self.assertEqual("recon", report["no_findings"]["source_stage"])
        self.assertEqual("test-operator", report["no_findings"]["reviewer"])
        self.assertTrue(report["no_findings"]["safety"]["no_finding_bodies"])
        self.assertFalse(report["no_findings"]["safety"]["issue_bodies_created"])
        self.assertEqual("example/demo", report["no_findings"]["target_metadata"]["repo"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Findings: 0", cp_validate.stdout)

        cp_metrics = self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        self.assertIn("Findings: 0", cp_metrics.stdout)
        metrics = json.loads((run_dir / "reports" / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(0, metrics["findings"]["total"])
        self.assertTrue(metrics["summary"]["public_safe"])
        self.assertEqual(0, metrics["summary"]["findings_total"])
        self.assertEqual(0, metrics["summary"]["issue_recommended_findings"])
        self.assertTrue(metrics["summary"]["no_findings"]["recorded"])
        self.assertEqual("recon", metrics["summary"]["no_findings"]["source_stage"])
        self.assertTrue(metrics["summary"]["no_findings"]["recon_only"])

        cp_benchmark = self.run_cmd([REPO_ROOT / "bin" / "gra-benchmark", "--run", run_dir], check=True)
        self.assertIn("Findings: 0", cp_benchmark.stdout)
        benchmark = json.loads((run_dir / "reports" / "benchmark.json").read_text(encoding="utf-8"))
        self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        refreshed_metrics = json.loads((run_dir / "reports" / "metrics.json").read_text(encoding="utf-8"))
        self.assertTrue(refreshed_metrics["summary"]["benchmark"]["artifact_present"])
        self.assertEqual(benchmark["summary"]["gate_count"], refreshed_metrics["summary"]["benchmark"]["gate_count"])
        self.assertEqual(benchmark["summary"]["warnings"], refreshed_metrics["summary"]["benchmark"]["warnings"])

        cp_graph = self.run_cmd([REPO_ROOT / "bin" / "gra-evidence-graph", "--run", run_dir], check=True)
        self.assertIn("Nodes:", cp_graph.stdout)
        graph = json.loads((run_dir / "reports" / "evidence-graph.json").read_text(encoding="utf-8"))
        self.assertEqual(0, graph["summary"]["high_critical_issue_recommended_findings"])
        self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        graph_metrics = json.loads((run_dir / "reports" / "metrics.json").read_text(encoding="utf-8"))
        self.assertTrue(graph_metrics["summary"]["evidence_graph"]["artifact_present"])
        self.assertEqual(len(graph["nodes"]), graph_metrics["summary"]["evidence_graph"]["node_count"])
        self.assertEqual(len(graph["edges"]), graph_metrics["summary"]["evidence_graph"]["edge_count"])

        cp_issues = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--dry-run",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed,Probable,Potential,Informational",
            ],
            check=True,
        )
        self.assertIn("Wrote", cp_issues.stdout)
        issue_result = json.loads((run_dir / "issues-created.json").read_text(encoding="utf-8"))
        self.assertTrue(issue_result["dry_run"])
        self.assertEqual([], issue_result["created"])

        cp_existing = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-no-findings",
                "--run",
                run_dir,
                "--rationale",
                "Second write should require explicit force.",
            ]
        )
        self.assertEqual(2, cp_existing.returncode)
        self.assertIn("findings.json already exists", cp_existing.stderr)

    def test_gra_workflow_profile_marks_recon_only_scoped_skips_for_reporting(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")

        cp_profile = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-workflow-profile",
                "--run",
                run_dir,
                "--profile",
                "recon-only",
                "--reviewer",
                "test-operator",
                "--rationale",
                "Reconnaissance completed and advanced validation stages are intentionally out of scope.",
            ],
            check=True,
        )

        self.assertIn("Profile: recon-only", cp_profile.stdout)
        self.assertIn("Skipped by scope:", cp_profile.stdout)
        profile = json.loads((run_dir / "reports" / "workflow-profile.json").read_text(encoding="utf-8"))
        self.assertEqual("gra-workflow-profile", profile["source"])
        self.assertEqual("recon-only", profile["profile"])
        self.assertEqual("test-operator", profile["reviewer"])
        self.assertTrue(profile["safety"]["local_artifacts_only"])
        self.assertFalse(profile["safety"]["raw_evidence_copied"])
        self.assertFalse(profile["safety"]["issue_bodies_created"])
        self.assertGreater(profile["summary"]["skipped_by_scope_count"], 0)
        self.assertIn("adversarial_validation", profile["summary"]["scoped_skip_stages"])
        self.assertIn("remediation", profile["summary"]["scoped_skip_stages"])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Workflow profile: validated", cp_validate.stdout)

        cp_metrics = self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        self.assertIn("Workflow profile skipped by scope:", cp_metrics.stdout)
        metrics = json.loads((run_dir / "reports" / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual("recon-only", metrics["workflow_profile"]["profile"])
        self.assertEqual(profile["summary"]["skipped_by_scope_count"], metrics["workflow_profile"]["skipped_by_scope_count"])
        self.assertEqual(profile["summary"]["skipped_by_scope_count"], metrics["summary"]["workflow_profile"]["skipped_by_scope_count"])

        cp_benchmark = self.run_cmd([REPO_ROOT / "bin" / "gra-benchmark", "--run", run_dir], check=True)
        self.assertIn("Workflow skipped by scope:", cp_benchmark.stdout)
        benchmark = json.loads((run_dir / "reports" / "benchmark.json").read_text(encoding="utf-8"))
        self.assertEqual("recon-only", benchmark["metrics"]["summary"]["workflow_profile"])
        self.assertEqual(
            profile["summary"]["skipped_by_scope_count"],
            benchmark["metrics"]["summary"]["workflow_skipped_by_scope_count"],
        )

        cp_graph = self.run_cmd([REPO_ROOT / "bin" / "gra-evidence-graph", "--run", run_dir], check=True)
        self.assertIn("Nodes:", cp_graph.stdout)
        graph = json.loads((run_dir / "reports" / "evidence-graph.json").read_text(encoding="utf-8"))
        self.assertEqual("recon-only", graph["summary"]["workflow_profile"]["profile"])
        self.assertEqual(profile["summary"]["skipped_by_scope_count"], graph["summary"]["workflow_profile"]["skipped_by_scope_count"])
        node_types = {node["type"] for node in graph["nodes"]}
        self.assertIn("workflow_profile", node_types)
        self.assertIn("workflow_stage", node_types)

        cp_final_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Metrics: validated", cp_final_validate.stdout)
        self.assertIn("Workflow profile: validated", cp_final_validate.stdout)
        self.assertIn("Benchmark: validated", cp_final_validate.stdout)
        self.assertIn("Evidence graph: validated", cp_final_validate.stdout)

    def test_gra_no_findings_rejects_symlinked_reports_dir(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        shutil.rmtree(run_dir / "reports")
        outside = self.work_dir / "outside-reports"
        outside.mkdir()
        (run_dir / "reports").symlink_to(outside, target_is_directory=True)

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-no-findings",
                "--run",
                run_dir,
                "--source-stage",
                "recon",
                "--rationale",
                "Bounded reconnaissance completed with no confirmed findings.",
            ]
        )

        self.assertEqual(2, cp.returncode)
        self.assertIn("reports_dir must not contain symlink components", cp.stderr)
        self.assertFalse((outside / "findings.json").exists())
        self.assertFalse((outside / "NO_FINDINGS.md").exists())

    def test_gra_trace_exec_with_consumer_run_writes_trace_artifacts(self) -> None:
        producer_run = self.copy_fixture_run("minimal-run")
        consumer_run = self.copy_fixture_run("minimal-run")
        consumer_ctx_path = consumer_run / "context.json"
        consumer_ctx = json.loads(consumer_ctx_path.read_text(encoding="utf-8"))
        consumer_ctx.update(
            {
                "repo": "example/consumer-api",
                "repo_slug": "example__consumer-api",
                "run_id": "consumer-fixture-run",
            }
        )
        consumer_ctx_path.write_text(json.dumps(consumer_ctx, indent=2) + "\n", encoding="utf-8")
        (consumer_run / "repo" / "routes").mkdir(parents=True, exist_ok=True)
        (consumer_run / "repo" / "routes" / "upload.py").write_text(
            "from shared_lib.parser import parse_user_input\n"
            "def upload(request):\n"
            "    return parse_user_input(request.body)\n",
            encoding="utf-8",
        )

        env, codex_log = self.env_with_codex_log(GRA_MOCK_FIXTURE_DIR=str(FIXTURES / "trace-output"))
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-trace",
                "--producer-run",
                producer_run,
                "--finding",
                "SEC-001",
                "--consumer-run",
                consumer_run,
                "--model",
                "gpt-fixture",
                "--effort",
                "medium",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Running Codex trace reachability for SEC-001", cp.stdout)
        self.assertIn("example/demo -> example/consumer-api", cp.stdout)
        self.assertIn("Codex status: 0", cp.stdout)

        subject = json.loads(
            (producer_run / "reports" / "traces" / "sec-001-example-consumer-api.subjects.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("SEC-001", subject["finding_id"])
        self.assertEqual("example/demo", subject["producer"]["repo"])
        self.assertEqual("example/consumer-api", subject["consumer"]["repo"])
        self.assertIn("required_trace_fields", subject["trace_contract"])

        prompt = producer_run / "prompts" / "exec" / "trace-reachability-sec-001-example-consumer-api.prompt.md"
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertIn("Trace results are reachability evidence, not exploit proof.", prompt_text)
        self.assertIn("No external scanning.", prompt_text)
        self.assertIn("No exploit payloads", prompt_text)
        self.assertIn("Trace subjects file: reports/traces/sec-001-example-consumer-api.subjects.json", prompt_text)
        self.assertIn("Consumer repository: example/consumer-api", prompt_text)
        self.assertIn("entry_points", prompt_text)
        self.assertIn("attacker_control", prompt_text)
        self.assertIn("reachable", prompt_text)
        self.assertIn("limitations", prompt_text)
        self.assertNotIn("{{", prompt_text)

        traces = json.loads((producer_run / "reports" / "traces.json").read_text(encoding="utf-8"))
        self.assertEqual("TRACE-001", traces["traces"][0]["id"])
        self.assertEqual("SEC-001", traces["traces"][0]["finding_id"])
        self.assertEqual("example/consumer-api", traces["traces"][0]["consumer_repo"])
        trace_md = (producer_run / "reports" / "TRACE.md").read_text(encoding="utf-8")
        self.assertIn("reachability evidence, not exploit proof", trace_md)
        self.assertIn("TRACE-001", trace_md)

        final_path = producer_run / "codex-trace-sec-001-example-consumer-api-final.md"
        events_path = producer_run / "codex-trace-sec-001-example-consumer-api-events.jsonl"
        stderr_path = producer_run / "codex-trace-sec-001-example-consumer-api-stderr.txt"
        for output_path in [
            producer_run / "reports" / "traces" / "sec-001-example-consumer-api.subjects.json",
            producer_run / "reports" / "traces.json",
            producer_run / "reports" / "TRACE.md",
            producer_run / "prompts" / "exec" / "trace-reachability-sec-001-example-consumer-api.prompt.md",
            final_path,
            events_path,
            stderr_path,
        ]:
            self.assert_path_under(output_path, producer_run)
        self.assertEqual(final_path.read_text(encoding="utf-8"), "mock codex mode=success\n")
        self.assertIn('"status": "ok"', events_path.read_text(encoding="utf-8"))
        self.assertTrue(stderr_path.exists())
        calls = self.read_codex_calls(codex_log)
        self.assertEqual(len(calls), 1, calls)
        self.assertIn(str(final_path), calls[0])
        self.assertIn('model_reasoning_effort="medium"', calls[0])
        self.assertIn("sandbox_workspace_write.network_access=false", calls[0])

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", producer_run], check=True)
        self.assertIn("Traces: validated", cp_validate.stdout)

    def test_gra_trace_prepare_invalid_finding_fails_before_clone(self) -> None:
        producer_run = self.copy_fixture_run("minimal-run")
        env, gh_log = self.env_with_gh_log()

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-trace",
                "--producer-run",
                producer_run,
                "--finding",
                "SEC-404",
                "--consumer-repo",
                "example/consumer-api",
                "--mode",
                "prepare",
            ],
            env=env,
        )

        self.assertEqual(2, cp.returncode)
        self.assertIn("finding not found: SEC-404", cp.stderr)
        self.assertEqual([], [call for call in self.read_gh_calls(gh_log) if call[:2] == ["repo", "clone"]])

    def test_gra_trace_exec_and_goal_require_consumer_run_without_cloning(self) -> None:
        producer_run = self.copy_fixture_run("minimal-run")
        env, gh_log = self.env_with_gh_log()

        for mode in ["exec", "goal"]:
            cp = self.run_cmd(
                [
                    REPO_ROOT / "bin" / "gra-trace",
                    "--producer-run",
                    producer_run,
                    "--finding",
                    "SEC-001",
                    "--consumer-repo",
                    "example/consumer-api",
                    "--mode",
                    mode,
                ],
                env=env,
            )
            self.assertEqual(2, cp.returncode)
            self.assertIn(f"--mode {mode} requires --consumer-run", cp.stderr)

        self.assertEqual([], [call for call in self.read_gh_calls(gh_log) if call[:2] == ["repo", "clone"]])

    def test_gra_trace_rejects_reports_dir_path_traversal(self) -> None:
        producer_run = self.copy_fixture_run("minimal-run")
        consumer_run = self.copy_fixture_run("minimal-run")
        ctx_path = producer_run / "context.json"
        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        ctx["reports_dir"] = "../outside-reports"
        ctx_path.write_text(json.dumps(ctx, indent=2) + "\n", encoding="utf-8")
        env, codex_log = self.env_with_codex_log(GRA_MOCK_FIXTURE_DIR=str(FIXTURES / "trace-output"))

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-trace",
                "--producer-run",
                producer_run,
                "--finding",
                "SEC-001",
                "--consumer-run",
                consumer_run,
            ],
            env=env,
        )

        self.assertEqual(2, cp.returncode)
        self.assertIn("reports_dir must not contain path traversal", cp.stderr)
        self.assertFalse((self.work_dir / "outside-reports").exists())
        self.assertEqual([], self.read_codex_calls(codex_log))

    def test_gra_trace_rejects_repo_dir_path_traversal(self) -> None:
        producer_run = self.copy_fixture_run("minimal-run")
        consumer_run = self.copy_fixture_run("minimal-run")
        ctx_path = producer_run / "context.json"
        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        ctx["repo_dir"] = "../outside-repo"
        ctx_path.write_text(json.dumps(ctx, indent=2) + "\n", encoding="utf-8")
        env, codex_log = self.env_with_codex_log(GRA_MOCK_FIXTURE_DIR=str(FIXTURES / "trace-output"))

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-trace",
                "--producer-run",
                producer_run,
                "--finding",
                "SEC-001",
                "--consumer-run",
                consumer_run,
            ],
            env=env,
        )

        self.assertEqual(2, cp.returncode)
        self.assertIn("repo_dir must not contain path traversal", cp.stderr)
        self.assertEqual([], self.read_codex_calls(codex_log))

    def test_gra_trace_rejects_symlinked_producer_reports_dir(self) -> None:
        producer_run = self.copy_fixture_run("minimal-run")
        consumer_run = self.copy_fixture_run("minimal-run")
        outside_reports = self.work_dir / "outside-reports"
        shutil.move(str(producer_run / "reports"), outside_reports)
        os.symlink(outside_reports, producer_run / "reports", target_is_directory=True)
        env, codex_log = self.env_with_codex_log(GRA_MOCK_FIXTURE_DIR=str(FIXTURES / "trace-output"))

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-trace",
                "--producer-run",
                producer_run,
                "--finding",
                "SEC-001",
                "--consumer-run",
                consumer_run,
            ],
            env=env,
        )

        self.assertEqual(2, cp.returncode)
        self.assertIn("reports_dir", cp.stderr)
        self.assertEqual([], self.read_codex_calls(codex_log))

    def test_gra_trace_rejects_symlinked_consumer_run(self) -> None:
        producer_run = self.copy_fixture_run("minimal-run")
        consumer_run = self.copy_fixture_run("minimal-run")
        consumer_link = self.work_dir / "consumer-run-link"
        os.symlink(consumer_run, consumer_link, target_is_directory=True)
        env, codex_log = self.env_with_codex_log(GRA_MOCK_FIXTURE_DIR=str(FIXTURES / "trace-output"))

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-trace",
                "--producer-run",
                producer_run,
                "--finding",
                "SEC-001",
                "--consumer-run",
                consumer_link,
            ],
            env=env,
        )

        self.assertEqual(2, cp.returncode)
        self.assertIn("consumer run must not be a symlink", cp.stderr)
        self.assertEqual([], self.read_codex_calls(codex_log))

    def test_gra_trace_keeps_network_disabled_and_docs_experimental_p3(self) -> None:
        cp_help = self.run_cmd([REPO_ROOT / "bin" / "gra-trace", "--help"], check=True)
        self.assertNotIn("--network", cp_help.stdout)

        producer_run = self.copy_fixture_run("minimal-run")
        consumer_run = self.copy_fixture_run("minimal-run")
        cp_network = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-trace",
                "--producer-run",
                producer_run,
                "--finding",
                "SEC-001",
                "--consumer-run",
                consumer_run,
                "--network",
            ]
        )
        self.assertEqual(2, cp_network.returncode)
        self.assertIn("unrecognized arguments: --network", cp_network.stderr)

        docs_to_check = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "docs" / "TRACE_REACHABILITY.md",
            REPO_ROOT / "docs" / "COMMAND_REFERENCE.md",
            REPO_ROOT / "docs" / "MULTI_REPO.md",
            REPO_ROOT / "docs" / "STAGED_AGENTIC_WORKFLOW.md",
        ]
        for doc in docs_to_check:
            text = doc.read_text(encoding="utf-8")
            self.assertIn("gra-trace", text, doc)
            self.assertIn("experimental/P3", text, doc)

    def test_gra_trace_prepare_clones_consumer_repo_and_prepares_goal_prompt(self) -> None:
        producer_run = self.copy_fixture_run("minimal-run")
        env, gh_log = self.env_with_gh_log()
        env["GRA_MOCK_TARGET_REPO_DIR"] = str(FIXTURES / "adversarial-repos" / "direct-readme")
        codex_log = self.work_dir / "trace-prepare-codex.jsonl"
        env["GRA_MOCK_CODEX_LOG"] = str(codex_log)

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-trace",
                "--producer-run",
                producer_run,
                "--finding",
                "SEC-001",
                "--consumer-repo",
                "example/consumer-api",
                "--mode",
                "prepare",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Prepared cross-repo trace reachability workspace.", cp.stdout)
        self.assertIn("Next exec command:", cp.stdout)

        consumer_run = producer_run / "trace-consumers" / "example__consumer-api"
        self.assertTrue((consumer_run / "repo" / ".git").exists())
        self.assertEqual("example/consumer-api", json.loads((consumer_run / "context.json").read_text(encoding="utf-8"))["repo"])
        prompt = producer_run / "prompts" / "goal" / "trace-reachability-sec-001-example-consumer-api.goal.md"
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertTrue(prompt_text.startswith("/goal "))
        self.assertIn("Trace subjects file: reports/traces/sec-001-example-consumer-api.subjects.json", prompt_text)
        self.assertIn("reachability", prompt_text)
        self.assertNotIn("{{", prompt_text)
        self.assertEqual(self.read_codex_calls(codex_log), [])
        calls = self.read_gh_calls(gh_log)
        self.assert_gh_called(calls, ["repo", "clone"])

        repo_dir = consumer_run / "repo"
        subprocess.run(
            ["git", "-C", str(repo_dir), "checkout", "-b", "feature-trace"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        (repo_dir / "feature.txt").write_text("feature branch fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_dir), "add", "feature.txt"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(
            ["git", "-C", str(repo_dir), "-c", "commit.gpgsign=false", "commit", "-m", "feature trace"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        feature_commit = subprocess.check_output(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], text=True).strip()
        subprocess.run(
            ["git", "-C", str(repo_dir), "checkout", "main"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        cp_branch = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-trace",
                "--producer-run",
                producer_run,
                "--finding",
                "SEC-001",
                "--consumer-repo",
                "example/consumer-api",
                "--mode",
                "prepare",
                "--branch",
                "feature-trace",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Prepared cross-repo trace reachability workspace.", cp_branch.stdout)
        current_branch = subprocess.check_output(["git", "-C", str(repo_dir), "branch", "--show-current"], text=True).strip()
        self.assertEqual("feature-trace", current_branch)
        branch_ctx = json.loads((consumer_run / "context.json").read_text(encoding="utf-8"))
        self.assertEqual("feature-trace", branch_ctx["branch"])
        self.assertEqual(feature_commit, branch_ctx["commit"])
        clone_calls = [call for call in self.read_gh_calls(gh_log) if call[:2] == ["repo", "clone"]]
        self.assertEqual(1, len(clone_calls), clone_calls)
