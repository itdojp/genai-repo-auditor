from __future__ import annotations

import sqlite3

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403


class PublicationWorkflowTests(CliWorkflowTestCase):
    def test_gra_issues_dry_run_and_verified_plan_support_custom_reports_dir(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        default_reports = run_dir / "reports"
        custom_reports = run_dir / "custom-reports"
        default_reports.rename(custom_reports)
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "custom-reports"
        context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        findings_path = custom_reports / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"][0]["issue_body_file"] = "custom-reports/issue-drafts/SEC-001.md"
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--dry-run", "--min-severity", "Low", "--statuses", "Confirmed"],
            check=True,
        )
        self.assertTrue((custom_reports / "issue-dry-run-summary.json").is_file())
        self.assertTrue((custom_reports / "ISSUE_DRY_RUN_SUMMARY.md").is_file())
        self.assertTrue((custom_reports / "issue-ledger.json").is_file())
        self.assertTrue((custom_reports / "duplicate-decisions" / "SEC-001.json").is_file())
        self.assertFalse(default_reports.exists())

        plan_path = custom_reports / "issue-publication-plan.json"
        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--plan", "--min-severity", "Low", "--statuses", "Confirmed"],
            check=True,
        )
        self.assertTrue(plan_path.is_file())
        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--apply-plan", plan_path, "--dry-run"],
            check=True,
        )
        summary = json.loads((custom_reports / "issue-dry-run-summary.json").read_text(encoding="utf-8"))
        self.assertEqual("verified-publication-plan", summary["selection_source"])
        events = self.read_command_events(run_dir)
        self.assertIn("custom-reports/issue-dry-run-summary.json", events[-1]["output_artifact_refs"])

    def test_gra_issues_replan_without_apply_plan_remains_preview(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--replan"], check=True)

        self.assertIn("Dry-run preview only", cp.stdout)
        self.assertFalse((run_dir / "reports" / "issue-publication-plan.json").exists())
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events))
        self.assert_public_command_event(events[0], command="gra-issues", phase="preview")
        self.assertNotIn("reports/issue-publication-plan.json", events[0]["output_artifact_refs"])

    def test_gra_issues_dry_run_and_apply_use_safe_fixture_issue_body(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--dry-run",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        self.assertIn("DRY RUN: would create issue for SEC-001", cp.stdout)
        self.assertIn("Dry-run preview only; no issue publication plan was written.", cp.stdout)
        self.assertIn("Preview plan path if promoted with --plan:", cp.stdout)
        self.assertIn("Preview issue publication entries:", cp.stdout)
        self.assertIn("Issue body SHA256:", cp.stdout)
        self.assertFalse((run_dir / "reports" / "issue-publication-plan.json").exists())
        result = json.loads((run_dir / "issues-created.json").read_text(encoding="utf-8"))
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["preview_only"])
        self.assertFalse(result["plan_written"])
        self.assertFalse(result["plan_verified"])
        self.assertEqual(result["publication_plan_status"], "not-written-preview")
        self.assertIsNone(result["plan_path"])
        self.assertEqual(result["preview_plan_path"], str(run_dir / "reports" / "issue-publication-plan.json"))
        self.assertIsNone(result["plan_sha256"])
        self.assertEqual(result["created"][0]["id"], "SEC-001")
        self.assertEqual(result["created"][0]["fingerprint"], FIXTURE_FINGERPRINT)
        self.assertEqual(len(result["created"][0]["issue_body_sha256"]), 64)
        self.assertEqual(result["created"][0]["issue_body_sha256"], result["created"][0]["issue_body_sha256"].lower())
        ledger = json.loads((run_dir / "reports" / "issue-ledger.json").read_text(encoding="utf-8"))
        self.assertFalse(ledger["plan_written"])
        self.assertEqual(ledger["publication_plan_status"], "not-written-preview")
        self.assertEqual(ledger["findings"][0]["publication_status"], "dry-run")
        self.assertIsNone(ledger["findings"][0]["source_plan"])
        self.assertIsNone(ledger["findings"][0]["plan_sha256"])
        decision_path = run_dir / "reports" / "duplicate-decisions" / "SEC-001.json"
        self.assertTrue(decision_path.is_file())
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        self.assertEqual(decision["finding_id"], "SEC-001")
        self.assertEqual(decision["fingerprint"], FIXTURE_FINGERPRINT)
        self.assertEqual(decision["decision"], "new")
        self.assertFalse(decision["exact_match"])
        self.assertEqual(len(decision["root_cause_fingerprint"]), 24)
        self.assertEqual(len(decision["source_to_sink_fingerprint"]), 24)
        preview_events = self.read_command_events(run_dir)
        self.assertEqual(1, len(preview_events))
        self.assert_public_command_event(preview_events[0], command="gra-issues", phase="preview")
        self.assertIn("reports/findings.json", preview_events[0]["input_artifact_refs"])
        self.assertIn("reports/issue-ledger.json", preview_events[0]["output_artifact_refs"])
        self.assertIn("issues-created.json", preview_events[0]["output_artifact_refs"])
        self.assertIn("reports/issue-dry-run-summary.json", preview_events[0]["output_artifact_refs"])
        self.assertIn("reports/ISSUE_DRY_RUN_SUMMARY.md", preview_events[0]["output_artifact_refs"])
        preview_event_text = json.dumps(preview_events)
        self.assertNotIn("Fixture issue body", preview_event_text)
        self.assertNotIn("issue_body", preview_event_text)

        apply_run = self.copy_fixture_run("minimal-run")
        cp_apply = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                apply_run,
                "--apply",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        self.assertIn("CREATED SEC-001", cp_apply.stdout)
        apply_events = self.read_command_events(apply_run)
        self.assertEqual(1, len(apply_events))
        self.assert_public_command_event(apply_events[0], command="gra-issues", phase="execute")
        self.assertFalse((apply_run / "reports" / "issue-dry-run-summary.json").exists())

    def test_gra_issues_dry_run_summary_partitions_selection_without_github(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        data = json.loads(findings_path.read_text(encoding="utf-8"))
        original = data["findings"][0]

        low = dict(original, id="SEC-LOW", fingerprint="fixture-low", severity="Low", issue_body_file="")
        potential = dict(original, id="SEC-POTENTIAL", fingerprint="fixture-potential", status="Potential", issue_body_file="")
        not_recommended = dict(original, id="SEC-NOISSUE", fingerprint="fixture-noissue", issue_recommended=False, issue_body_file="")
        novelty = dict(original, id="SEC-NOVELTY", fingerprint="fixture-novelty", issue_body_file="")
        data["findings"] = [original, low, potential, not_recommended, novelty]
        findings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        (run_dir / "reports" / "known-findings.json").write_text(
            json.dumps(
                {
                    "findings": [
                        {
                            "finding_id": "SEC-NOVELTY",
                            "fingerprint": "fixture-novelty",
                            "novelty_status": "duplicate",
                            "issue_recommended": False,
                        }
                    ]
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        env, log_path = self.env_with_gh_log()

        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--dry-run",
                "--min-severity",
                "Medium",
                "--statuses",
                "Confirmed",
            ],
            env=env,
            check=True,
        )

        summary_path = run_dir / "reports" / "issue-dry-run-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "total_candidates": 5,
                "selected": 1,
                "filtered_by_severity_or_status": 2,
                "issue_recommendation_suppressed": 1,
                "novelty_suppressed": 1,
                "duplicate_suppressed": 0,
                "advanced_validation_blocked": 0,
                "public_visibility_blocked": 0,
                "would_create": 1,
                "warnings": 2,
                "issues_created": 0,
            },
            summary["counts"],
        )
        self.assertEqual("current-findings", summary["selection_source"])
        self.assertEqual([], self.read_gh_calls(log_path))
        summary_text = summary_path.read_text(encoding="utf-8")
        for forbidden in ["Fixture command injection", "app.py", FIXTURE_FINGERPRINT, "test-fixture"]:
            self.assertNotIn(forbidden, summary_text)
        self.assertFalse((run_dir / "reports" / "issue-publication-plan.json").exists())

    def test_gra_issues_dry_run_summary_counts_local_ledger_duplicate_without_github(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        issue_url = "https://github.example.invalid/example/demo/issues/262"
        apply_env, _apply_log = self.env_with_gh_log(GRA_MOCK_ISSUE_URL=issue_url)
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
            env=apply_env,
            check=True,
        )
        dry_env, dry_log = self.env_with_gh_log()
        if dry_log.exists():
            dry_log.unlink()
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--dry-run",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
                "--require-advanced-validation",
            ],
            env=dry_env,
            check=True,
        )
        summary = json.loads((run_dir / "reports" / "issue-dry-run-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(1, summary["counts"]["duplicate_suppressed"])
        self.assertEqual(0, summary["counts"]["advanced_validation_blocked"])
        self.assertEqual(0, summary["counts"]["would_create"])
        self.assertEqual([], self.read_gh_calls(dry_log))

    def test_gra_issues_dry_run_summary_counts_public_and_strict_advanced_blocks(self) -> None:
        public_run = self.copy_fixture_run("minimal-run")
        context_path = public_run / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["visibility"] = "PUBLIC"
        context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-issues", "--run", public_run, "--dry-run", "--min-severity", "Low", "--statuses", "Confirmed"],
            check=True,
        )
        public_summary = json.loads((public_run / "reports" / "issue-dry-run-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(1, public_summary["counts"]["public_visibility_blocked"])
        self.assertEqual(0, public_summary["counts"]["would_create"])

        unknown_run = self.copy_fixture_run("minimal-run")
        unknown_context_path = unknown_run / "context.json"
        unknown_context = json.loads(unknown_context_path.read_text(encoding="utf-8"))
        unknown_context["visibility"] = "UNKNOWN"
        unknown_context_path.write_text(json.dumps(unknown_context, indent=2) + "\n", encoding="utf-8")
        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-issues", "--run", unknown_run, "--dry-run", "--min-severity", "Low", "--statuses", "Confirmed"],
            check=True,
        )
        unknown_summary = json.loads((unknown_run / "reports" / "issue-dry-run-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(1, unknown_summary["counts"]["public_visibility_blocked"])
        self.assertEqual(0, unknown_summary["counts"]["would_create"])

        strict_run = self.copy_fixture_run("minimal-run")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                strict_run,
                "--dry-run",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
                "--require-advanced-validation",
            ]
        )
        self.assertEqual(4, cp.returncode, cp.stderr)
        strict_summary = json.loads((strict_run / "reports" / "issue-dry-run-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(1, strict_summary["counts"]["advanced_validation_blocked"])
        self.assertEqual(0, strict_summary["counts"]["would_create"])
        self.assertEqual(0, strict_summary["counts"]["issues_created"])

    def test_gra_issues_zero_finding_dry_run_writes_explicit_zero_counts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        data = json.loads(findings_path.read_text(encoding="utf-8"))
        data["findings"] = []
        findings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--dry-run"],
            check=True,
        )

        summary = json.loads((run_dir / "reports" / "issue-dry-run-summary.json").read_text(encoding="utf-8"))
        self.assertTrue(all(value == 0 for value in summary["counts"].values()))
        self.assertFalse((run_dir / "reports" / "issue-publication-plan.json").exists())

    def test_gra_validate_report_rejects_invalid_or_symlinked_dry_run_summary(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--dry-run", "--min-severity", "Low", "--statuses", "Confirmed"],
            check=True,
        )
        summary_path = run_dir / "reports" / "issue-dry-run-summary.json"
        valid = json.loads(summary_path.read_text(encoding="utf-8"))

        invalid_payloads = []
        unknown = json.loads(json.dumps(valid))
        unknown["unexpected"] = True
        invalid_payloads.append(unknown)
        negative = json.loads(json.dumps(valid))
        negative["counts"]["would_create"] = -1
        invalid_payloads.append(negative)
        inconsistent = json.loads(json.dumps(valid))
        inconsistent["counts"]["would_create"] = 0
        invalid_payloads.append(inconsistent)
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
                cp = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
                self.assertNotEqual(0, cp.returncode)
                self.assertIn("issue_dry_run_summary", cp.stderr)

        summary_path.write_text(json.dumps(valid, indent=2) + "\n", encoding="utf-8")
        markdown_path = run_dir / "reports" / "ISSUE_DRY_RUN_SUMMARY.md"
        markdown_path.write_text("# stale or partial summary\n", encoding="utf-8")
        cp_mismatch = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertNotEqual(0, cp_mismatch.returncode)
        self.assertIn("JSON and Markdown summaries do not match", cp_mismatch.stderr)

        outside = self.work_dir / "outside-dry-run-summary.json"
        outside.write_text(json.dumps(valid, indent=2) + "\n", encoding="utf-8")
        summary_path.unlink()
        summary_path.symlink_to(outside)
        cp_symlink = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertNotEqual(0, cp_symlink.returncode)
        self.assertIn("symlink", cp_symlink.stderr.lower())

    def test_gra_issues_duplicate_decisions_distinguish_variant_and_related_candidates(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"][0]["variant_of"] = "SEC-ROOT"
        related = dict(findings["findings"][0])
        related.update(
            {
                "id": "SEC-002",
                "fingerprint": "fixture-related-fingerprint-0002",
                "issue_title": "[Security][High] Related but distinct fixture finding",
                "issue_body_file": "",
                "variant_of": "",
                "related_issue_numbers": [10, "https://github.example.invalid/example/demo/issues/11"],
            }
        )
        findings["findings"].append(related)
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--dry-run",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )

        variant_decision = json.loads((run_dir / "reports" / "duplicate-decisions" / "SEC-001.json").read_text(encoding="utf-8"))
        related_decision = json.loads((run_dir / "reports" / "duplicate-decisions" / "SEC-002.json").read_text(encoding="utf-8"))
        self.assertEqual(variant_decision["decision"], "variant")
        self.assertEqual(variant_decision["variant_of"], ["SEC-ROOT"])
        self.assertEqual(related_decision["decision"], "related-not-duplicate")
        self.assertEqual(related_decision["candidate_issue_numbers"], [10, 11])

    def test_gra_issues_plan_and_apply_plan_bind_exact_issue_content(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        cp_plan = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        self.assertIn("Wrote issue publication plan", cp_plan.stdout)
        self.assertIn("issue_body_sha256=", cp_plan.stdout)
        self.assertTrue(plan_path.is_file())
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertEqual(plan["schema_version"], "1")
        self.assertEqual(plan["repo"], "example/demo")
        self.assertEqual(plan["selected_findings"][0]["id"], "SEC-001")
        self.assertEqual(plan["selected_findings"][0]["fingerprint"], FIXTURE_FINGERPRINT)
        self.assertEqual(plan["selected_findings"][0]["issue_body_file"], "reports/issue-drafts/SEC-001.md")
        self.assertFalse((run_dir / "issues-created.json").exists())
        plan_events = self.read_command_events(run_dir)
        self.assertEqual(1, len(plan_events))
        self.assert_public_command_event(plan_events[0], command="gra-issues", phase="plan")
        self.assertIn("reports/issue-publication-plan.json", plan_events[0]["output_artifact_refs"])

        cp_verify = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
                "--dry-run",
            ],
            check=True,
        )
        self.assertIn("Dry-run preview only; verified issue publication plan was not applied.", cp_verify.stdout)
        verified_summary = json.loads((run_dir / "reports" / "issue-dry-run-summary.json").read_text(encoding="utf-8"))
        self.assertEqual("verified-publication-plan", verified_summary["selection_source"])
        self.assertEqual(1, verified_summary["counts"]["total_candidates"])
        self.assertEqual(1, verified_summary["counts"]["would_create"])
        self.assertEqual(0, verified_summary["counts"]["issues_created"])
        verification_events = self.read_command_events(run_dir)
        self.assertEqual(2, len(verification_events))
        self.assert_public_command_event(verification_events[1], command="gra-issues", phase="verify-plan")
        self.assertIn("reports/issue-publication-plan.json", verification_events[1]["input_artifact_refs"])

        issue_url = "https://github.example.invalid/example/demo/issues/60"
        env, log_path = self.env_with_gh_log(GRA_MOCK_ISSUE_URL=issue_url)
        cp_apply = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
            ],
            env=env,
            check=True,
        )
        self.assertIn("Verified issue publication plan", cp_apply.stdout)
        self.assertIn(f"CREATED SEC-001: {issue_url}", cp_apply.stdout)
        result = json.loads((run_dir / "issues-created.json").read_text(encoding="utf-8"))
        self.assertFalse(result["dry_run"])
        self.assertFalse(result["preview_only"])
        self.assertFalse(result["plan_written"])
        self.assertTrue(result["plan_verified"])
        self.assertEqual(result["publication_plan_status"], "verified-existing-plan-applied")
        self.assertEqual(result["plan_path"], str(plan_path))
        self.assertEqual(len(result["plan_sha256"]), 64)
        self.assertEqual(result["created"][0]["fingerprint"], FIXTURE_FINGERPRINT)
        publication_events = self.read_command_events(run_dir)
        self.assertEqual(3, len(publication_events))
        self.assert_public_command_event(publication_events[2], command="gra-issues", phase="apply-plan")
        self.assertIn("reports/issue-publication-plan.json", publication_events[2]["input_artifact_refs"])
        self.assertIn("issues-created.json", publication_events[2]["output_artifact_refs"])
        calls = self.read_gh_calls(log_path)
        self.assert_gh_called(calls, ["repo", "view"])
        self.assert_gh_called(calls, ["issue", "list"])
        self.assert_gh_called(calls, ["issue", "create"])

    def test_gra_issues_plan_writes_canonical_issue_ledger_for_all_findings(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        low = dict(findings["findings"][0])
        low.update(
            {
                "id": "SEC-002",
                "fingerprint": "fixture-fingerprint-low-0002",
                "severity": "Low",
                "issue_title": "[Security][Low] Low severity fixture finding",
                "issue_body_file": "",
            }
        )
        findings["findings"].append(low)
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )

        self.assertIn("Wrote issue ledger", cp.stdout)
        ledger_path = run_dir / "reports" / "issue-ledger.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["schema_version"], "1")
        self.assertEqual(ledger["repo"], "example/demo")
        self.assertTrue(ledger["plan_written"])
        self.assertEqual(ledger["publication_plan_status"], "written")
        entries = {entry["finding_id"]: entry for entry in ledger["findings"]}
        self.assertEqual(sorted(entries), ["SEC-001", "SEC-002"])
        self.assertEqual(entries["SEC-001"]["publication_status"], "pending")
        self.assertEqual(entries["SEC-001"]["source_plan"], "reports/issue-publication-plan.json")
        self.assertEqual(len(entries["SEC-001"]["plan_sha256"]), 64)
        self.assertEqual(entries["SEC-001"]["body_hash"], entries["SEC-001"]["body_hash"].lower())
        self.assertEqual(entries["SEC-002"]["publication_status"], "not-selected")
        self.assertEqual(entries["SEC-002"]["selection_reason"], "severity below High")
        self.assertIsNone(entries["SEC-002"]["url"])
        cp_valid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Issue ledger: validated", cp_valid.stdout)

    def test_gra_issues_apply_plan_is_idempotent_from_issue_ledger(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        issue_url = "https://github.example.invalid/example/demo/issues/72"
        env, _first_log = self.env_with_gh_log(GRA_MOCK_ISSUE_URL=issue_url)
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
            ],
            env=env,
            check=True,
        )

        second_env, second_log = self.env_with_gh_log()
        if second_log.exists():
            second_log.unlink()
        cp_second = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
            ],
            env=second_env,
            check=True,
        )

        self.assertIn(f"SKIP ledger SEC-001: {issue_url}", cp_second.stdout)
        result = json.loads((run_dir / "issues-created.json").read_text(encoding="utf-8"))
        self.assertEqual(result["created"], [])
        self.assertEqual(result["skipped"][0]["reason"], "ledger")
        calls = self.read_gh_calls(second_log)
        self.assert_gh_called(calls, ["repo", "view"])
        self.assert_gh_not_called(calls, ["issue", "list"])
        self.assert_gh_not_called(calls, ["issue", "create"])

    def test_gra_issues_ledger_prevents_same_finding_id_duplicate_after_fingerprint_drift(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        issue_url = "https://github.example.invalid/example/demo/issues/76"
        env, _first_log = self.env_with_gh_log(GRA_MOCK_ISSUE_URL=issue_url)
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

        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"][0]["fingerprint"] = "fixture-fingerprint-drift-0076"
        findings["findings"][0]["issue_body_file"] = ""
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

        second_env, second_log = self.env_with_gh_log()
        if second_log.exists():
            second_log.unlink()
        cp_second = self.run_cmd(
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
            env=second_env,
            check=True,
        )

        self.assertIn(f"SKIP ledger SEC-001: {issue_url}", cp_second.stdout)
        calls = self.read_gh_calls(second_log)
        self.assert_gh_called(calls, ["repo", "view"])
        self.assert_gh_not_called(calls, ["issue", "list"])
        self.assert_gh_not_called(calls, ["issue", "create"])
        ledger = json.loads((run_dir / "reports" / "issue-ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(len(ledger["findings"]), 1)
        entry = ledger["findings"][0]
        self.assertEqual(entry["finding_id"], "SEC-001")
        self.assertEqual(entry["fingerprint"], "fixture-fingerprint-drift-0076")
        self.assertEqual(entry["previous_fingerprint"], FIXTURE_FINGERPRINT)
        self.assertEqual(entry["url"], issue_url)
        self.assertIn("current fingerprint differs from published ledger fingerprint", entry["drift"])

    def test_gra_issues_verify_ledger_detects_github_drift(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        issue_url = "https://github.example.invalid/example/demo/issues/73"
        env, _apply_log = self.env_with_gh_log(GRA_MOCK_ISSUE_URL=issue_url)
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
            ],
            env=env,
            check=True,
        )

        drift_env, drift_log = self.env_with_gh_log()
        cp_drift = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--verify-ledger",
            ],
            env=drift_env,
        )
        self.assertEqual(cp_drift.returncode, 4, cp_drift.stderr)
        self.assertIn("Issue ledger drift detected", cp_drift.stderr)
        self.assertIn("no open GitHub issue found", cp_drift.stderr)
        self.assert_gh_called(self.read_gh_calls(drift_log), ["issue", "list"])

        ok_env, _ok_log = self.env_with_gh_log(GRA_MOCK_EXISTING_ISSUE_URL=issue_url)
        cp_ok = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--verify-ledger",
            ],
            env=ok_env,
            check=True,
        )
        self.assertIn("Issue ledger verified", cp_ok.stdout)
        verify_events = self.read_command_events(run_dir)
        self.assert_public_command_event(verify_events[-1], command="gra-issues", phase="verify-ledger")
        self.assertIn("reports/issue-ledger.json", verify_events[-1]["input_artifact_refs"])
        self.assertIn("reports/duplicate-decisions/SEC-001.json", verify_events[-1]["input_artifact_refs"])
        self.assertEqual([], verify_events[-1]["output_artifact_refs"])

    def test_gra_issues_verify_ledger_requires_existing_ledger(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--verify-ledger"])
        self.assertEqual(cp.returncode, 2, cp.stderr)
        self.assertIn("issue ledger not found", cp.stderr)

    def test_gra_issues_verify_ledger_requires_duplicate_decision_for_published_issue(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        issue_url = "https://github.example.invalid/example/demo/issues/77"
        env, _apply_log = self.env_with_gh_log(GRA_MOCK_ISSUE_URL=issue_url)
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
            ],
            env=env,
            check=True,
        )
        shutil.rmtree(run_dir / "reports" / "duplicate-decisions")

        verify_env, _verify_log = self.env_with_gh_log(GRA_MOCK_EXISTING_ISSUE_URL=issue_url)
        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--verify-ledger"], env=verify_env)

        self.assertEqual(cp.returncode, 4, cp.stderr)
        self.assertIn("duplicate decision record missing", cp.stderr)

    def test_gra_store_imports_issue_ledger_when_present(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        issue_url = "https://github.example.invalid/example/demo/issues/75"
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
        db_path = self.work_dir / "ledger-store.sqlite"
        self.run_cmd([REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", db_path], check=True)

        with sqlite3.connect(db_path) as conn:
            row = conn.execute("select finding_id, fingerprint, url, data_json from issues").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[:3], ("SEC-001", FIXTURE_FINGERPRINT, issue_url))
        stored = json.loads(row[3])
        self.assertEqual(stored["publication_status"], "published")
        self.assertEqual(stored["body_hash"], stored["body_hash"].lower())

    def test_gra_issues_plan_includes_advanced_validation_summary(self) -> None:
        run_dir = self.copy_fixture_run("advanced-workflow-run")
        self.copy_advanced_workflow_outputs(run_dir)
        plan_path = run_dir / "reports" / "issue-publication-plan.json"

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "High",
                "--statuses",
                "Confirmed,Probable",
            ],
            check=True,
        )

        self.assertIn("advanced_validation:", cp.stdout)
        self.assertIn("WARNING: related adversarial validation has blocking decision(s): VAL-102=downgrade", cp.stdout)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        selected = {entry["id"]: entry for entry in plan["selected_findings"]}
        self.assertEqual(sorted(selected), ["SEC-101", "SEC-102"])

        sec101 = selected["SEC-101"]
        self.assertEqual(sec101["chain_membership"], ["CHAIN-001"])
        self.assertEqual(sec101["advanced_validation"]["chains"]["matched"], ["CHAIN-001"])
        self.assertEqual(sec101["advanced_validation"]["chains"]["missing"], [])
        self.assertEqual(sec101["advanced_validation"]["adversarial_validation"]["finding_validations"], ["VAL-101"])
        self.assertTrue(sec101["advanced_validation"]["adversarial_validation"]["exists"])
        self.assertEqual(sec101["advanced_validation"]["safe_local_proof"]["proofs"], ["PROOF-101"])
        self.assertTrue(sec101["advanced_validation"]["safe_local_proof"]["exists"])
        self.assertFalse(sec101["advanced_validation"]["safe_local_proof"]["not_applicable"])
        self.assertEqual(sec101["advanced_validation"]["warnings"], [])

        sec102 = selected["SEC-102"]
        self.assertEqual(sec102["advanced_validation"]["adversarial_validation"]["finding_validations"], ["VAL-102"])
        self.assertEqual(
            sec102["advanced_validation"]["adversarial_validation"]["finding_validation_details"],
            [
                {
                    "id": "VAL-102",
                    "decision": "downgrade",
                    "recommended_severity": "Medium",
                    "recommended_confidence": "Low",
                }
            ],
        )
        self.assertEqual(sec102["advanced_validation"]["adversarial_validation"]["blocking_decisions"], ["VAL-102=downgrade"])
        self.assertEqual(sec102["advanced_validation"]["safe_local_proof"]["proofs"], ["PROOF-102"])
        self.assertEqual(
            sec102["advanced_validation"]["warnings"],
            ["related adversarial validation has blocking decision(s): VAL-102=downgrade"],
        )

    def test_gra_issues_require_advanced_validation_fails_when_artifacts_are_missing(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        plan_path = run_dir / "reports" / "issue-publication-plan.json"

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--require-advanced-validation",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ]
        )

        self.assertEqual(cp.returncode, 4, cp.stderr)
        self.assertIn("Advanced validation requirements failed", cp.stderr)
        self.assertIn("SEC-001: High/Critical issue-recommended finding lacks related adversarial validation", cp.stderr)
        self.assertIn("SEC-001: High/Critical issue-recommended finding lacks safe local proof", cp.stderr)
        self.assertFalse(plan_path.exists())

    def test_gra_issues_require_advanced_validation_rejects_blocking_validation_decisions(self) -> None:
        run_dir = self.copy_fixture_run("advanced-workflow-run")
        self.copy_advanced_workflow_outputs(run_dir)
        plan_path = run_dir / "reports" / "issue-publication-plan.json"

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--require-advanced-validation",
                "--min-severity",
                "High",
                "--statuses",
                "Confirmed,Probable",
            ]
        )

        self.assertEqual(cp.returncode, 4, cp.stderr)
        self.assertIn("SEC-102: related adversarial validation has blocking decision(s): VAL-102=downgrade", cp.stderr)
        self.assertFalse(plan_path.exists())

    def test_gra_issues_accepts_explicit_safe_proof_not_applicable_reason(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"][0]["safe_proof_not_applicable"] = True
        findings["findings"][0]["safe_proof_not_applicable_reason"] = "configuration-only finding reviewed by policy owner"
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")
        (run_dir / "reports" / "validation.json").write_text(
            json.dumps(
                {
                    "run_id": "fixture-run",
                    "repo": "example/demo",
                    "generated_at": "2026-05-27T00:00:00Z",
                    "validations": [
                        {
                            "id": "VAL-001",
                            "subject_type": "finding",
                            "subject_id": "SEC-001",
                            "decision": "confirm",
                            "original_severity": "High",
                            "recommended_severity": "High",
                            "original_confidence": "High",
                            "recommended_confidence": "High",
                            "reasoning_summary": "Fixture validation for not-applicable proof handling.",
                            "evidence_checked": ["reports/findings.json"],
                            "missing_evidence": [],
                            "safe_validation_steps": ["policy-owner review"],
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        plan_path = run_dir / "reports" / "issue-publication-plan.json"

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--require-advanced-validation",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )

        self.assertNotIn("WARNING:", cp.stdout)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        proof = plan["selected_findings"][0]["advanced_validation"]["safe_local_proof"]
        self.assertFalse(proof["exists"])
        self.assertTrue(proof["not_applicable"])
        self.assertEqual(proof["not_applicable_reason"], "configuration-only finding reviewed by policy owner")

    def test_gra_issues_public_body_does_not_include_attack_chain_report_contents(self) -> None:
        run_dir = self.copy_fixture_run("advanced-workflow-run")
        self.copy_advanced_workflow_outputs(run_dir)
        validation_path = run_dir / "reports" / "validation.json"
        validations = json.loads(validation_path.read_text(encoding="utf-8"))
        for item in validations["validations"]:
            if item["subject_id"] == "SEC-102":
                item["decision"] = "confirm"
                item["recommended_severity"] = "High"
                item["recommended_confidence"] = "Medium"
        validation_path.write_text(json.dumps(validations, indent=2) + "\n", encoding="utf-8")
        marker = "DO_NOT_COPY_ATTACK_CHAIN_INTERNAL_DETAIL"
        (run_dir / "reports" / "ATTACK_CHAINS.md").write_text(
            f"# Internal chain report\n\n{marker}\n",
            encoding="utf-8",
        )
        capture_path = self.work_dir / "issue-body-capture.jsonl"
        env, log_path = self.env_with_gh_log(
            GRA_MOCK_GH_VISIBILITY="PUBLIC",
            GRA_MOCK_GH_BODY_CAPTURE=str(capture_path),
        )

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply",
                "--allow-public",
                "--require-advanced-validation",
                "--min-severity",
                "High",
                "--statuses",
                "Confirmed,Probable",
            ],
            env=env,
            check=True,
        )

        self.assertIn("CREATED SEC-101", cp.stdout)
        self.assertIn("CREATED SEC-102", cp.stdout)
        captures = self.read_jsonl_calls(capture_path)
        self.assertEqual(len(captures), 2)
        self.assertTrue(all(marker not in item["body"] for item in captures))
        self.assertTrue(all("ATTACK_CHAINS.md" not in item["body"] for item in captures))
        calls = self.read_gh_calls(log_path)
        self.assert_gh_called(calls, ["repo", "view"])
        self.assert_gh_called(calls, ["issue", "create"])

    def test_gra_issues_apply_plan_rejects_changed_advanced_validation_state(self) -> None:
        run_dir = self.copy_fixture_run("advanced-workflow-run")
        self.copy_advanced_workflow_outputs(run_dir)
        validation_path = run_dir / "reports" / "validation.json"
        validations = json.loads(validation_path.read_text(encoding="utf-8"))
        for item in validations["validations"]:
            if item["subject_id"] == "SEC-102":
                item["decision"] = "confirm"
                item["recommended_severity"] = "High"
                item["recommended_confidence"] = "Medium"
        validation_path.write_text(json.dumps(validations, indent=2) + "\n", encoding="utf-8")
        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--require-advanced-validation",
                "--min-severity",
                "High",
                "--statuses",
                "Confirmed,Probable",
            ],
            check=True,
        )
        validations = json.loads(validation_path.read_text(encoding="utf-8"))
        for item in validations["validations"]:
            if item["subject_id"] == "SEC-102":
                item["decision"] = "downgrade"
                item["recommended_severity"] = "Medium"
                item["recommended_confidence"] = "Low"
        validation_path.write_text(json.dumps(validations, indent=2) + "\n", encoding="utf-8")
        env, log_path = self.env_with_gh_log()

        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
            ],
            env=env,
        )

        self.assertEqual(cp.returncode, 4, cp.stderr)
        self.assertIn("Issue publication plan verification failed", cp.stderr)
        self.assertIn("SEC-102: advanced_validation changed after plan creation", cp.stderr)
        self.assert_gh_not_called(self.read_gh_calls(log_path), ["issue", "create"])

    def test_gra_issues_apply_plan_rejects_changed_issue_body(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        draft = run_dir / "reports" / "issue-drafts" / "SEC-001.md"
        draft.write_text(draft.read_text(encoding="utf-8") + "\nChanged after approval.\n", encoding="utf-8")
        env, log_path = self.env_with_gh_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
            ],
            env=env,
        )
        self.assertEqual(cp.returncode, 4, cp.stderr)
        self.assertIn("Issue publication plan verification failed", cp.stderr)
        self.assertIn("SEC-001: issue_body_sha256 changed after plan creation", cp.stderr)
        self.assertFalse((run_dir / "issues-created.json").exists())
        self.assert_gh_not_called(self.read_gh_calls(log_path), ["issue", "create"])

    def test_gra_issues_apply_plan_replan_refreshes_without_publishing(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        draft = run_dir / "reports" / "issue-drafts" / "SEC-001.md"
        draft.write_text(draft.read_text(encoding="utf-8") + "\nApproved content update before replanning.\n", encoding="utf-8")
        env, log_path = self.env_with_gh_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
                "--replan",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Rewrote issue publication plan", cp.stdout)
        self.assertIn("Review the refreshed issue publication plan before applying", cp.stderr)
        self.assertFalse((run_dir / "issues-created.json").exists())
        self.assertEqual(self.read_gh_calls(log_path), [])
        refreshed = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertEqual(refreshed["selected_findings"][0]["id"], "SEC-001")
        events = self.read_command_events(run_dir)
        self.assert_public_command_event(events[-1], command="gra-issues", phase="plan")
        self.assertNotIn("reports/issue-publication-plan.json", events[-1]["input_artifact_refs"])
        self.assertIn("reports/issue-publication-plan.json", events[-1]["output_artifact_refs"])
        self.assertNotIn("issues-created.json", events[-1]["output_artifact_refs"])

    def test_gra_issues_apply_plan_rejects_changed_fingerprint(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"][0]["fingerprint"] = "fedcba9876543210fedcba98"
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")
        env, log_path = self.env_with_gh_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
            ],
            env=env,
        )
        self.assertEqual(cp.returncode, 4, cp.stderr)
        self.assertIn("SEC-001: fingerprint changed after plan creation", cp.stderr)
        self.assert_gh_not_called(self.read_gh_calls(log_path), ["issue", "create"])

    def test_gra_issues_apply_plan_handles_duplicate_ids_by_fingerprint(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        duplicate = dict(findings["findings"][0])
        duplicate["fingerprint"] = "222222222222222222222222"
        duplicate["issue_title"] = "[Security][High] Duplicate ID but distinct fingerprint"
        duplicate["issue_body_file"] = "reports/issue-drafts/SEC-002.md"
        (run_dir / "reports" / "issue-drafts" / "SEC-002.md").write_text(
            "# Duplicate ID but distinct fingerprint\n\n"
            "<!-- genai-repo-auditor:fingerprint=222222222222222222222222 -->\n",
            encoding="utf-8",
        )
        findings["findings"].append(duplicate)
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")

        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertEqual([entry["id"] for entry in plan["selected_findings"]], ["SEC-001", "SEC-001"])
        self.assertEqual(
            [entry["fingerprint"] for entry in plan["selected_findings"]],
            [FIXTURE_FINGERPRINT, "222222222222222222222222"],
        )

        env, log_path = self.env_with_gh_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
            ],
            env=env,
            check=True,
        )
        self.assertIn("CREATED SEC-001", cp.stdout)
        result = json.loads((run_dir / "issues-created.json").read_text(encoding="utf-8"))
        self.assertEqual(len(result["created"]), 2)
        create_calls = [call for call in self.read_gh_calls(log_path) if call[:2] == ["issue", "create"]]
        self.assertEqual(len(create_calls), 2)

    def test_gra_issues_apply_plan_rejects_malformed_selected_entry(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["selected_findings"].append("not-an-object")
        plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
            ]
        )
        self.assertEqual(cp.returncode, 2, cp.stderr)
        self.assertIn("selected_findings[1] must be an object", cp.stderr)

    def test_gra_issues_apply_plan_preserves_public_repo_guard(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        plan_path = run_dir / "reports" / "issue-publication-plan.json"
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--plan",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        env, log_path = self.env_with_gh_log(GRA_MOCK_GH_VISIBILITY="PUBLIC")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply-plan",
                plan_path,
            ],
            env=env,
        )
        self.assertEqual(cp.returncode, 3, cp.stderr)
        self.assertIn("Refusing to create security issues", cp.stderr)
        denied_events = self.read_command_events(run_dir)
        self.assert_public_command_event(
            denied_events[-1],
            command="gra-issues",
            phase="apply-plan",
            exit_code=3,
            status="blocked",
        )
        self.assertEqual("publication_policy", denied_events[-1]["error_category"])
        calls = self.read_gh_calls(log_path)
        self.assert_gh_called(calls, ["repo", "view"])
        self.assert_gh_not_called(calls, ["issue", "list"])
        self.assert_gh_not_called(calls, ["issue", "create"])

    def test_gra_issues_apply_refuses_public_repo_without_allow_public(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, log_path = self.env_with_gh_log(GRA_MOCK_GH_VISIBILITY="PUBLIC")
        cp = self.run_cmd(
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
        )
        self.assertEqual(cp.returncode, 3, cp.stderr)
        self.assertIn("Refusing to create security issues", cp.stderr)
        self.assertIn("visibility=PUBLIC", cp.stderr)
        self.assertIn("Use --allow-public only when disclosure policy permits", cp.stderr)
        self.assertFalse((run_dir / "issues-created.json").exists())

        calls = self.read_gh_calls(log_path)
        self.assert_gh_called(calls, ["repo", "view"])
        self.assert_gh_not_called(calls, ["issue", "list"])
        self.assert_gh_not_called(calls, ["issue", "create"])

    def test_gra_issues_rejects_unsafe_event_path_before_github_mutation(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "../outside-reports"
        context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        env, log_path = self.env_with_gh_log(GRA_MOCK_GH_VISIBILITY="PRIVATE")

        cp = self.run_cmd(
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
        )

        self.assertEqual(2, cp.returncode)
        self.assertIn("command event preflight failed", cp.stderr)
        self.assertEqual([], self.read_gh_calls(log_path))
        self.assertFalse((run_dir / "issues-created.json").exists())

    def test_gra_issues_allow_public_apply_creates_issue_with_safe_fixture(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        issue_url = "https://github.example.invalid/example/demo/issues/41"
        env, log_path = self.env_with_gh_log(
            GRA_MOCK_GH_VISIBILITY="PUBLIC",
            GRA_MOCK_ISSUE_URL=issue_url,
        )
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply",
                "--allow-public",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            env=env,
            check=True,
        )
        self.assertIn(f"CREATED SEC-001: {issue_url}", cp.stdout)

        result = json.loads((run_dir / "issues-created.json").read_text(encoding="utf-8"))
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["visibility"], "PUBLIC")
        self.assertEqual(result["created"], [
            {
                "id": "SEC-001",
                "url": issue_url,
                "title": "[Security][High] Fixture command injection finding",
                "fingerprint": FIXTURE_FINGERPRINT,
            }
        ])
        self.assertEqual(result["skipped"], [])

        calls = self.read_gh_calls(log_path)
        self.assert_gh_called(calls, ["repo", "view"])
        self.assert_gh_called(calls, ["issue", "list"])
        self.assert_gh_called(calls, ["issue", "create"])

    def test_gra_issues_duplicate_fingerprint_skips_issue_creation(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        existing_url = "https://github.example.invalid/example/demo/issues/7"
        env, log_path = self.env_with_gh_log(GRA_MOCK_EXISTING_ISSUE_URL=existing_url)
        cp = self.run_cmd(
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
        self.assertIn(f"SKIP duplicate SEC-001: {existing_url}", cp.stdout)

        result = json.loads((run_dir / "issues-created.json").read_text(encoding="utf-8"))
        self.assertEqual(result["created"], [])
        self.assertEqual(result["skipped"], [
            {
                "id": "SEC-001",
                "reason": "duplicate",
                "url": existing_url,
                "fingerprint": FIXTURE_FINGERPRINT,
            }
        ])
        decision = json.loads((run_dir / "reports" / "duplicate-decisions" / "SEC-001.json").read_text(encoding="utf-8"))
        self.assertEqual(decision["decision"], "exact-duplicate")
        self.assertTrue(decision["exact_match"])
        self.assertEqual(decision["exact_match_source"], "github-fingerprint-search")
        self.assertEqual(decision["candidate_issue_numbers"], [7])
        ledger = json.loads((run_dir / "reports" / "issue-ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(ledger["findings"][0]["duplicate_decision_file"], "reports/duplicate-decisions/SEC-001.json")

        calls = self.read_gh_calls(log_path)
        self.assert_gh_called(calls, ["repo", "view"])
        self.assert_gh_called(calls, ["issue", "list"])
        self.assert_gh_not_called(calls, ["issue", "create"])

    def test_gra_issues_create_labels_uses_mocked_gh_label_updates(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, log_path = self.env_with_gh_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply",
                "--create-labels",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            env=env,
            check=True,
        )
        self.assertIn("CREATED SEC-001", cp.stdout)

        calls = self.read_gh_calls(log_path)
        label_names = [
            call[2]
            for call in calls
            if len(call) >= 3 and call[:2] == ["label", "create"]
        ]
        self.assertIn("security", label_names)
        self.assertIn("genai-audit", label_names)
        self.assertIn("severity-high", label_names)
        self.assertIn("status-confirmed", label_names)
        self.assertIn("category-command-injection", label_names)
        self.assertIn("test-fixture", label_names)
        self.assertTrue(
            all("--force" in call for call in calls if len(call) >= 3 and call[:2] == ["label", "create"]),
            f"label create calls must update existing labels with --force: {calls!r}",
        )
        self.assert_gh_called(calls, ["issue", "create"])

    def test_gra_issues_rejects_unsafe_issue_body_file_in_dry_run_and_apply(self) -> None:
        dry_run_dir = self.copy_fixture_run("minimal-run")
        dry_findings_path = dry_run_dir / "reports" / "findings.json"
        dry_data = json.loads(dry_findings_path.read_text(encoding="utf-8"))
        dry_data["findings"][0]["issue_body_file"] = "../../secret.md"
        dry_findings_path.write_text(json.dumps(dry_data, indent=2) + "\n", encoding="utf-8")
        cp_dry = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                dry_run_dir,
                "--dry-run",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ]
        )
        self.assertNotEqual(cp_dry.returncode, 0)
        self.assertIn("issue_body_file must not contain", cp_dry.stderr)

        apply_run = self.copy_fixture_run("minimal-run")
        apply_findings_path = apply_run / "reports" / "findings.json"
        apply_data = json.loads(apply_findings_path.read_text(encoding="utf-8"))
        apply_data["findings"][0]["issue_body_file"] = "/etc/passwd"
        apply_findings_path.write_text(json.dumps(apply_data, indent=2) + "\n", encoding="utf-8")
        cp_apply = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                apply_run,
                "--apply",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ]
        )
        self.assertNotEqual(cp_apply.returncode, 0)
        self.assertIn("issue_body_file must be relative under reports/issue-drafts", cp_apply.stderr)

    def test_gra_issues_rejects_symlinked_reports_parent(self) -> None:
        run_dir = self.work_dir / "symlink-parent-run"
        run_dir.mkdir()
        outside_reports = self.work_dir / "outside-reports"
        shutil.copytree(FIXTURES / "minimal-run" / "reports", outside_reports)
        (run_dir / "reports").symlink_to(outside_reports, target_is_directory=True)
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--dry-run",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ]
        )
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("command event preflight failed", cp.stderr)
        self.assertIn("artifact path must stay under the run directory", cp.stderr)
