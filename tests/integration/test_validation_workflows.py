from __future__ import annotations

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403


class ValidationWorkflowTests(CliWorkflowTestCase):
    def test_gra_validate_report_enforces_no_findings_safety_constants(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        findings_path.unlink()
        self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-no-findings",
                "--run",
                run_dir,
                "--source-stage",
                "recon",
                "--rationale",
                "Bounded reconnaissance completed with no confirmed findings.",
            ],
            check=True,
        )

        report = json.loads(findings_path.read_text(encoding="utf-8"))
        report["no_findings"]["safety"]["issue_bodies_created"] = True
        findings_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])

        self.assertNotEqual(0, cp.returncode)
        self.assertIn("findings.no_findings.safety.issue_bodies_created", cp.stderr)
        self.assertIn("does not match required constant False", cp.stderr)

    def test_validate_report_accepts_v1_metrics_without_compact_summary(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        metrics_path = run_dir / "reports" / "metrics.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        metrics.pop("summary")
        metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

        cp_validate = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)

        self.assertIn("Metrics: validated", cp_validate.stdout)

    def test_validate_report_trace_reachability_contract(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        traces = json.loads((FIXTURES / "trace-output" / "reports" / "traces.json").read_text(encoding="utf-8"))
        (run_dir / "reports" / "traces.json").write_text(json.dumps(traces, indent=2) + "\n", encoding="utf-8")

        cp_valid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertEqual(cp_valid.returncode, 0, cp_valid.stderr)
        self.assertIn("Traces: validated", cp_valid.stdout)

        invalid_run = self.copy_fixture_run("minimal-run")
        invalid = json.loads((FIXTURES / "trace-output" / "reports" / "traces.json").read_text(encoding="utf-8"))
        invalid["traces"] = [
            {
                **invalid["traces"][0],
                "id": "TRACE-1",
                "finding_id": "SEC-404",
                "entry_points": ["repo/routes/upload.py", 123],
                "attacker_control": "Yes",
                "reachable": "Maybe",
                "status": "Exploitable",
            }
        ]
        (invalid_run / "reports" / "traces.json").write_text(json.dumps(invalid, indent=2) + "\n", encoding="utf-8")

        cp_invalid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", invalid_run])
        self.assertNotEqual(cp_invalid.returncode, 0)
        self.assertIn("trace id must match", cp_invalid.stderr)
        self.assertIn("SEC-404", cp_invalid.stderr)
        self.assertIn("entry_points[1]", cp_invalid.stderr)
        self.assertIn("attacker_control", cp_invalid.stderr)
        self.assertIn("reachable", cp_invalid.stderr)
        self.assertIn("invalid status", cp_invalid.stderr)

    def test_validate_report_chain_references(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        chains = json.loads((FIXTURES / "chain-output" / "reports" / "chains.json").read_text(encoding="utf-8"))
        (run_dir / "reports" / "chains.json").write_text(json.dumps(chains, indent=2) + "\n", encoding="utf-8")

        cp_valid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertEqual(cp_valid.returncode, 0, cp_valid.stderr)
        self.assertIn("Chains: validated", cp_valid.stdout)

        invalid_run = self.copy_fixture_run("minimal-run")
        invalid = json.loads((FIXTURES / "chain-output" / "reports" / "chains.json").read_text(encoding="utf-8"))
        invalid["chains"][0]["findings"] = ["SEC-404"]
        invalid["chains"][0]["targets"] = ["TGT-404"]
        invalid["chains"][0]["scanner_refs"] = ["missing-scanner-ref"]
        (invalid_run / "reports" / "chains.json").write_text(json.dumps(invalid, indent=2) + "\n", encoding="utf-8")

        cp_invalid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", invalid_run])
        self.assertNotEqual(cp_invalid.returncode, 0)
        self.assertIn("SEC-404", cp_invalid.stderr)
        self.assertIn("TGT-404", cp_invalid.stderr)
        self.assertIn("missing-scanner-ref", cp_invalid.stderr)

    def test_validate_report_chain_scanner_refs_do_not_follow_symlinked_index(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        chains = json.loads((FIXTURES / "chain-output" / "reports" / "chains.json").read_text(encoding="utf-8"))
        chains["chains"][0]["findings"] = []
        chains["chains"][0]["targets"] = []
        chains["chains"][0]["scanner_refs"] = ["external-ref"]
        (run_dir / "reports" / "chains.json").write_text(json.dumps(chains, indent=2) + "\n", encoding="utf-8")

        scanner_dir = run_dir / "reports" / "scanner-results"
        scanner_dir.mkdir(parents=True, exist_ok=True)
        outside_index = self.work_dir / "outside-scanner-index.json"
        outside_index.write_text(
            json.dumps(
                {
                    "run_id": "fixture-run",
                    "repo": "example/demo",
                    "generated_at": "2026-05-26T00:00:00Z",
                    "results": [{"tool": "external-ref", "path": "reports/scanner-results/raw.json", "format": "json", "imported_at": "2026-05-26T00:00:01Z"}],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (scanner_dir / "scanner-index.json").symlink_to(outside_index)

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("scanner artifact path must not contain symlink components", cp.stderr)
        self.assertIn("external-ref", cp.stderr)
        self.assertIn("is not present in reports/scanner-results/scanner-index.json", cp.stderr)

    def test_validate_report_safe_proofs_rejects_unsafe_values(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        proofs = json.loads((FIXTURES / "proof-output" / "reports" / "proofs.json").read_text(encoding="utf-8"))
        proofs_dir = run_dir / "reports" / "proofs"
        proofs_dir.mkdir(parents=True, exist_ok=True)
        (proofs_dir / "SEC-001-test-plan.md").write_text("# Safe local proof\n", encoding="utf-8")
        (run_dir / "reports" / "proofs.json").write_text(json.dumps(proofs, indent=2) + "\n", encoding="utf-8")

        cp_valid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertEqual(cp_valid.returncode, 0, cp_valid.stderr)
        self.assertIn("Proofs: validated", cp_valid.stdout)

        invalid_run = self.copy_fixture_run("minimal-run")
        invalid = json.loads((FIXTURES / "proof-output" / "reports" / "proofs.json").read_text(encoding="utf-8"))
        invalid["proofs"][0]["finding_id"] = "SEC-404"
        invalid["proofs"][0]["proof_type"] = "exploit-script"
        invalid["proofs"][0]["safe_by_design"] = False
        invalid["proofs"][0]["files_created"] = ["reports/proofs/../../repo/exploit.py"]
        invalid["proofs"][0]["commands_run"] = ["curl https://example.com/payload; rm -rf repo"]
        (invalid_run / "reports" / "proofs.json").write_text(json.dumps(invalid, indent=2) + "\n", encoding="utf-8")

        cp_invalid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", invalid_run])
        self.assertNotEqual(cp_invalid.returncode, 0)
        self.assertIn("SEC-404", cp_invalid.stderr)
        self.assertIn("invalid proof type", cp_invalid.stderr)
        self.assertIn("safe_by_design", cp_invalid.stderr)
        self.assertIn("proof artifact path must not contain '..'", cp_invalid.stderr)
        self.assertIn("free-form shell strings are not accepted", cp_invalid.stderr)
        self.assertIn("shell metacharacters", cp_invalid.stderr)

        unsafe_structured_run = self.copy_fixture_run("minimal-run")
        unsafe_structured = json.loads((FIXTURES / "proof-output" / "reports" / "proofs.json").read_text(encoding="utf-8"))
        unsafe_structured["proofs"][0]["commands_run"] = [
            {
                "argv": ["python3", "-c", "import urllib.request; urllib.request.urlopen('https://example.com')"],
                "read_only": False,
                "writes": ["repo/output.txt"],
                "network": True,
                "requires_credentials": True,
                "cwd_scope": "external",
            },
            {
                "argv": ["python3", "-m", "json.tool", "reports/findings.json", "reports/proofs/out.json"],
                "read_only": True,
                "writes": [],
                "network": False,
                "requires_credentials": False,
                "cwd_scope": "run",
            },
            {
                "argv": ["python3", "-m", "json.tool", "--help"],
                "read_only": True,
                "writes": [],
                "network": False,
                "requires_credentials": False,
                "cwd_scope": "run",
            },
            {
                "argv": ["sed", "-i", "s/a/b/", "repo/app.py"],
                "read_only": True,
                "writes": [],
                "network": False,
                "requires_credentials": False,
                "cwd_scope": "target_repo",
            },
            {
                "argv": ["sed", "-n", "1w /tmp/proof", "repo/app.py"],
                "read_only": True,
                "writes": [],
                "network": False,
                "requires_credentials": False,
                "cwd_scope": "target_repo",
            },
            {
                "argv": ["sed", "-n", "1,20p", "--expression", "1w /tmp/proof", "repo/app.py"],
                "read_only": True,
                "writes": [],
                "network": False,
                "requires_credentials": False,
                "cwd_scope": "target_repo",
            },
            {
                "argv": ["rg", "--pre", "cat", "SEC-001", "repo/app.py"],
                "read_only": True,
                "writes": [],
                "network": False,
                "requires_credentials": False,
                "cwd_scope": "target_repo",
            },
        ]
        (unsafe_structured_run / "reports" / "proofs.json").write_text(
            json.dumps(unsafe_structured, indent=2) + "\n",
            encoding="utf-8",
        )

        cp_unsafe_structured = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-validate-report", "--run", unsafe_structured_run]
        )
        self.assertNotEqual(cp_unsafe_structured.returncode, 0)
        self.assertIn("read_only: must be true", cp_unsafe_structured.stderr)
        self.assertIn("writes: read-only proof commands must declare no writes", cp_unsafe_structured.stderr)
        self.assertIn("network: must be false", cp_unsafe_structured.stderr)
        self.assertIn("requires_credentials: must be false", cp_unsafe_structured.stderr)
        self.assertIn("cwd_scope: must be one of", cp_unsafe_structured.stderr)
        self.assertIn("python proof commands are limited to read-only JSON inspection", cp_unsafe_structured.stderr)
        self.assertIn("python -c is not allowed", cp_unsafe_structured.stderr)
        self.assertIn("python json.tool input file must not be an option", cp_unsafe_structured.stderr)
        self.assertIn("sed in-place editing is not allowed", cp_unsafe_structured.stderr)
        self.assertIn("sed proof commands are limited to read-only", cp_unsafe_structured.stderr)
        self.assertIn("sed proof command file arguments must not include additional options", cp_unsafe_structured.stderr)
        self.assertIn("rg --pre/--pre-glob is not allowed", cp_unsafe_structured.stderr)

        wrong_type_run = self.copy_fixture_run("minimal-run")
        (wrong_type_run / "reports" / "proofs.json").write_text("[]\n", encoding="utf-8")
        cp_wrong_type = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", wrong_type_run])
        self.assertNotEqual(cp_wrong_type.returncode, 0)
        self.assertIn("proofs: expected type object, got array", cp_wrong_type.stderr)
        self.assertNotIn("Traceback", cp_wrong_type.stderr)

    def test_validate_report_accepts_valid_fixture_and_rejects_invalid_fixtures(self) -> None:
        valid_run = self.copy_fixture_run("minimal-run")
        cp_valid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", valid_run])
        self.assertEqual(cp_valid.returncode, 0, cp_valid.stderr)
        self.assertIn("Findings: 1", cp_valid.stdout)

        invalid_findings_run = self.copy_fixture_run("invalid-findings-run")
        cp_invalid_findings = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", invalid_findings_run])
        self.assertNotEqual(cp_invalid_findings.returncode, 0)
        self.assertIn("invalid severity", cp_invalid_findings.stderr)
        self.assertIn("issue_recommended must be boolean", cp_invalid_findings.stderr)

        invalid_targets_run = self.copy_fixture_run("invalid-targets-run")
        cp_invalid_targets = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", invalid_targets_run])
        self.assertNotEqual(cp_invalid_targets.returncode, 0)
        self.assertIn("target id must match", cp_invalid_targets.stderr)
        self.assertIn("priority must be integer", cp_invalid_targets.stderr)

        empty_run = self.copy_fixture_run("minimal-run")
        empty_findings_path = empty_run / "reports" / "findings.json"
        empty_findings = json.loads(empty_findings_path.read_text(encoding="utf-8"))
        empty_findings["findings"] = []
        empty_findings_path.write_text(json.dumps(empty_findings, indent=2) + "\n", encoding="utf-8")
        cp_empty = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", empty_run])
        self.assertEqual(cp_empty.returncode, 0, cp_empty.stderr)
        self.assertIn("Findings: 0", cp_empty.stdout)

    def test_validate_report_target_quality_fields(self) -> None:
        valid_run = self.copy_fixture_run("minimal-run")
        targets_path = valid_run / "reports" / "targets.json"
        targets_data = json.loads(targets_path.read_text(encoding="utf-8"))
        target = targets_data["targets"][0]
        target.update(
            {
                "attack_class": "Authz",
                "attacker_model": "authenticated tenant user",
                "security_invariants": [
                    "Every tenant-scoped read must filter by tenant_id derived from the session."
                ],
                "max_files": 6,
                "expected_output": "finding-or-no-finding-with-coverage",
                "chain_relevance": "possible-link",
                "coverage": {
                    "review_depth": "shallow",
                    "files_reviewed": ["repo/app.py"],
                    "files_skipped": ["repo/legacy_app.py"],
                    "commands_run": ["python3 -m unittest"],
                    "unresolved_questions": ["Could not confirm legacy route ordering."],
                    "gapfill_recommended": True,
                    "gapfill_reason": "High-risk command surface only partially reviewed.",
                },
            }
        )
        targets_path.write_text(json.dumps(targets_data, indent=2) + "\n", encoding="utf-8")

        cp_valid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", valid_run])
        self.assertEqual(cp_valid.returncode, 0, cp_valid.stderr)
        self.assertIn("Targets: validated", cp_valid.stdout)

        invalid_run = self.copy_fixture_run("minimal-run")
        invalid_targets_path = invalid_run / "reports" / "targets.json"
        invalid_targets_data = json.loads(invalid_targets_path.read_text(encoding="utf-8"))
        invalid_target = invalid_targets_data["targets"][0]
        invalid_target.update(
            {
                "security_invariants": ["valid invariant", 123],
                "max_files": 0,
                "expected_output": "finding-only",
                "chain_relevance": "exploit-chain",
                "coverage": {
                    "review_depth": "broad",
                    "files_reviewed": ["valid", 123],
                    "gapfill_recommended": "yes",
                    "gapfill_reason": ["not", "string"],
                },
            }
        )
        invalid_targets_path.write_text(json.dumps(invalid_targets_data, indent=2) + "\n", encoding="utf-8")

        cp_invalid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", invalid_run])
        self.assertNotEqual(cp_invalid.returncode, 0)
        self.assertIn("security_invariants[1]", cp_invalid.stderr)
        self.assertIn("max_files must be between 1 and 20", cp_invalid.stderr)
        self.assertIn("expected_output", cp_invalid.stderr)
        self.assertIn("chain_relevance", cp_invalid.stderr)
        self.assertIn("coverage.review_depth", cp_invalid.stderr)
        self.assertIn("coverage.files_reviewed[1]", cp_invalid.stderr)
        self.assertIn("coverage.gapfill_recommended", cp_invalid.stderr)
        self.assertIn("coverage.gapfill_reason", cp_invalid.stderr)

    def test_validate_report_finding_assessment_fields(self) -> None:
        valid_run = self.copy_fixture_run("minimal-run")
        findings_path = valid_run / "reports" / "findings.json"
        findings_data = json.loads(findings_path.read_text(encoding="utf-8"))
        finding = findings_data["findings"][0]
        finding.update(
            {
                "bug_existence": "Confirmed",
                "attacker_reachability": "Probable",
                "boundary_crossing": "Potential",
                "impact_assessment": "Not assessed",
                "chain_membership": ["CHAIN-001"],
                "assessment_notes": {
                    "bug_existence": "The unsafe subprocess call exists in the fixture.",
                    "attacker_reachability": "Fixture route suggests user-controlled command input.",
                    "boundary_crossing": "Potential process execution boundary crossing.",
                    "impact_assessment": "Impact was not executed in the fixture.",
                },
            }
        )
        findings_path.write_text(json.dumps(findings_data, indent=2) + "\n", encoding="utf-8")

        cp_valid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", valid_run])
        self.assertEqual(cp_valid.returncode, 0, cp_valid.stderr)

        cp_dashboard = self.run_cmd([REPO_ROOT / "bin" / "gra-dashboard", "--run", valid_run], check=True)
        self.assertIn("dashboard.html", cp_dashboard.stdout)
        dashboard = (valid_run / "reports" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Finding assessment dimensions", dashboard)
        self.assertIn("Attacker reachability", dashboard)
        self.assertIn("Probable", dashboard)

        cp_sarif = self.run_cmd([REPO_ROOT / "bin" / "gra-sarif", "--run", valid_run], check=True)
        self.assertIn("findings.sarif", cp_sarif.stdout)
        sarif = json.loads((valid_run / "reports" / "findings.sarif").read_text(encoding="utf-8"))
        result_props = sarif["runs"][0]["results"][0]["properties"]
        self.assertEqual("Confirmed", result_props["bug_existence"])
        self.assertEqual(["CHAIN-001"], result_props["chain_membership"])
        self.assertEqual("Impact was not executed in the fixture.", result_props["assessment_notes"]["impact_assessment"])

        invalid_run = self.copy_fixture_run("minimal-run")
        invalid_findings_path = invalid_run / "reports" / "findings.json"
        invalid_data = json.loads(invalid_findings_path.read_text(encoding="utf-8"))
        invalid_finding = invalid_data["findings"][0]
        invalid_finding.update(
            {
                "bug_existence": "Yes",
                "attacker_reachability": "Reachable",
                "boundary_crossing": "Maybe",
                "impact_assessment": "Severe",
                "chain_membership": ["CHAIN-1", 123],
                "assessment_notes": {
                    "bug_existence": 123,
                },
            }
        )
        invalid_findings_path.write_text(json.dumps(invalid_data, indent=2) + "\n", encoding="utf-8")

        cp_invalid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", invalid_run])
        self.assertNotEqual(cp_invalid.returncode, 0)
        self.assertIn("findings.findings[0].bug_existence", cp_invalid.stderr)
        self.assertIn("invalid assessment value", cp_invalid.stderr)
        self.assertIn("chain_membership[0]", cp_invalid.stderr)
        self.assertIn("chain_membership[1]", cp_invalid.stderr)
        self.assertIn("assessment_notes.bug_existence", cp_invalid.stderr)

    def test_validate_report_adversarial_validation_decisions(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        base = findings["findings"][0]
        findings["findings"].extend(
            [
                {**base, "id": "SEC-002", "fingerprint": "fixture-fingerprint-1002", "severity": "High", "status": "Probable"},
                {**base, "id": "SEC-003", "fingerprint": "fixture-fingerprint-1003", "severity": "High", "status": "Potential"},
            ]
        )
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")
        validation = {
            "run_id": "fixture-run",
            "repo": "example/demo",
            "branch": "main",
            "commit": "0000000000000000000000000000000000000000",
            "generated_at": "2026-05-26T00:00:00Z",
            "validations": [
                {
                    "id": "VAL-001",
                    "subject_type": "finding",
                    "subject_id": "SEC-001",
                    "decision": "downgrade",
                    "original_severity": "High",
                    "recommended_severity": "Medium",
                    "original_confidence": "High",
                    "recommended_confidence": "Medium",
                    "reasoning_summary": "Reachability evidence is incomplete.",
                    "evidence_checked": ["reports/findings.json"],
                    "missing_evidence": ["production route wiring"],
                    "safe_validation_steps": ["static call-path review"],
                },
                {
                    "id": "VAL-002",
                    "subject_type": "finding",
                    "subject_id": "SEC-002",
                    "decision": "invalidate",
                    "original_severity": "High",
                    "recommended_severity": "Informational",
                    "original_confidence": "Medium",
                    "recommended_confidence": "Low",
                    "reasoning_summary": "Framework guard blocks the fixture path.",
                    "evidence_checked": ["repo/app.py"],
                    "missing_evidence": [],
                    "safe_validation_steps": ["review framework guard documentation in repository"],
                },
                {
                    "id": "VAL-003",
                    "subject_type": "finding",
                    "subject_id": "SEC-003",
                    "decision": "needs-human-review",
                    "original_severity": "High",
                    "recommended_severity": "High",
                    "original_confidence": "Low",
                    "recommended_confidence": "Low",
                    "reasoning_summary": "Middleware ordering cannot be proven from local evidence.",
                    "evidence_checked": ["reports/findings.json", "repo/app.py"],
                    "missing_evidence": ["deployed middleware order"],
                    "safe_validation_steps": ["ask maintainer to confirm deployment configuration"],
                },
            ],
        }
        (run_dir / "reports" / "validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")

        cp_valid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertEqual(cp_valid.returncode, 0, cp_valid.stderr)
        self.assertIn("Adversarial validations: validated", cp_valid.stdout)

        invalid_run = self.copy_fixture_run("minimal-run")
        invalid_validation = validation.copy()
        invalid_validation["validations"] = [
            {**validation["validations"][0], "decision": "promote", "subject_id": "SEC-404", "evidence_checked": [123]},
        ]
        (invalid_run / "reports" / "validation.json").write_text(
            json.dumps(invalid_validation, indent=2) + "\n",
            encoding="utf-8",
        )
        cp_invalid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", invalid_run])
        self.assertNotEqual(cp_invalid.returncode, 0)
        self.assertIn("invalid decision", cp_invalid.stderr)
        self.assertIn("not present in reports/findings.json", cp_invalid.stderr)
        self.assertIn("evidence_checked[0]", cp_invalid.stderr)

    def test_validate_report_rejects_safety_invalid_fields(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        data = json.loads(findings_path.read_text(encoding="utf-8"))
        finding = data["findings"][0]
        finding["fingerprint"] = "fingerprint-001"
        finding["generated_at"] = "not-a-date"
        finding["affected_locations"][0]["file"] = "../secret.py"
        finding["affected_locations"][0]["line"] = 0
        finding["issue_body_file"] = "../../secret.md"
        finding.pop("public_disclosure_risk", None)
        data["generated_at"] = "not-a-date"
        data["evidence_secret_probe"] = "AKIA" + "ABCDEFGHIJKLMNOP"
        findings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("findings.generated_at", cp.stderr)
        self.assertIn("fingerprint must not be a placeholder", cp.stderr)
        self.assertIn("affected_locations[0].file", cp.stderr)
        self.assertIn("line must be a positive integer", cp.stderr)
        self.assertIn("issue_body_file must not contain", cp.stderr)
        self.assertIn("public_disclosure_risk", cp.stderr)
        self.assertIn("obvious unredacted full secret value", cp.stderr)

    def test_validate_report_rejects_symlink_issue_body(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        draft_path = run_dir / "reports" / "issue-drafts" / "SEC-001.md"
        draft_path.unlink()
        outside = self.work_dir / "outside.md"
        outside.write_text("outside content\n", encoding="utf-8")
        draft_path.symlink_to(outside)
        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("issue_body_file must not be a symlink", cp.stderr)

    def test_validate_report_rejects_duplicate_ledger_with_non_duplicate_decision(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        existing_url = "https://github.example.invalid/example/demo/issues/78"
        env, _log_path = self.env_with_gh_log(GRA_MOCK_EXISTING_ISSUE_URL=existing_url)
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
        decision_path = run_dir / "reports" / "duplicate-decisions" / "SEC-001.json"
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        decision["decision"] = "new"
        decision_path.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])

        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("requires exact-duplicate decision", cp.stderr)
