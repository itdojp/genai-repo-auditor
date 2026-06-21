from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
VALIDATOR_PATH = REPO_ROOT / "bin" / "gra-validate-report"
SCHEMAS = REPO_ROOT / "templates" / "reports"


def load_validator() -> types.ModuleType:
    loader = importlib.machinery.SourceFileLoader("gra_validate_report_contract", str(VALIDATOR_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("unable to load gra-validate-report module spec")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


VALIDATOR = load_validator()


class ReportContractTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def copy_run(self, fixture_name: str = "minimal-run") -> Path:
        dst = self.work_dir / fixture_name
        shutil.copytree(FIXTURES / fixture_name, dst)
        return dst

    def load_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def write_run_manifest(self, run_dir: Path) -> dict[str, Any]:
        subprocess.run(
            [
                sys.executable,
                REPO_ROOT / "lib" / "run_manifest.py",
                "--lab-root",
                REPO_ROOT,
                "--run-dir",
                run_dir,
                "--command-name",
                "gra-audit",
                "--mode",
                "exec",
                "--model",
                "fixture-model",
                "--effort",
                "medium",
                "--depth",
                "1",
                "--network-allowed",
                "false",
                "--codex-json",
                "false",
                "--allow-invalid-report",
                "false",
                "--execution-phase",
                "completed",
                "--codex-status",
                "0",
                "--validation-status",
                "0",
                "--final-status",
                "0",
            ],
            cwd=REPO_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return self.load_json(run_dir / "run-manifest.json")

    def write_scanner_index(
        self,
        run_dir: Path,
        *,
        leads: list[dict[str, Any]] | None = None,
        entry_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        scanner_dir = run_dir / "reports" / "scanner-results"
        normalized_dir = scanner_dir / "normalized"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        raw_path = scanner_dir / "semgrep.json"
        raw_path.write_text('{"results": []}\n', encoding="utf-8")
        leads = leads if leads is not None else [{"rule_id": "fixture.rule", "raw_result_ref": "reports/scanner-results/semgrep.json"}]
        normalization = {"parse_error": "", "results_truncated": False}
        normalized = {
            "tool": "semgrep",
            "raw_result_ref": "reports/scanner-results/semgrep.json",
            "raw_bytes": raw_path.stat().st_size,
            "format": "json",
            "normalization": normalization,
            "leads": leads,
        }
        normalized_path = normalized_dir / "semgrep-leads.json"
        self.write_json(normalized_path, normalized)
        entry = {
            "tool": "semgrep",
            "path": "reports/scanner-results/semgrep.json",
            "format": "json",
            "imported_at": "2026-05-16T00:00:01Z",
            "sha256": "abc123",
            "raw_bytes": raw_path.stat().st_size,
            "normalized_path": "reports/scanner-results/normalized/semgrep-leads.json",
            "normalized_leads_count": len(leads),
            "normalization": normalization,
            "note": "fixture",
        }
        if entry_overrides:
            entry.update(entry_overrides)
        scanner_index = {
            "run_id": "fixture-run",
            "repo": "example/demo",
            "generated_at": "2026-05-16T00:00:00Z",
            "results": [entry],
        }
        self.write_json(scanner_dir / "scanner-index.json", scanner_index)
        return scanner_index

    def run_validator(self, run_dir: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, VALIDATOR_PATH, "--run", run_dir],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )

    def test_schema_required_fields_stay_aligned_with_validator_contracts(self) -> None:
        findings_schema = self.load_json(SCHEMAS / "findings.schema.json")
        target_schema = self.load_json(SCHEMAS / "targets.schema.json")
        scanner_schema = self.load_json(SCHEMAS / "scanner-index.schema.json")
        manifest_schema = self.load_json(SCHEMAS / "run-manifest.schema.json")
        dependencies_schema = self.load_json(SCHEMAS / "dependencies.schema.json")
        validation_schema = self.load_json(SCHEMAS / "validation.schema.json")
        chains_schema = self.load_json(SCHEMAS / "chains.schema.json")
        proofs_schema = self.load_json(SCHEMAS / "proofs.schema.json")
        remediation_schema = self.load_json(SCHEMAS / "remediation-candidates.schema.json")
        traces_schema = self.load_json(SCHEMAS / "traces.schema.json")
        metrics_schema = self.load_json(SCHEMAS / "metrics.schema.json")
        issue_ledger_schema = self.load_json(SCHEMAS / "issue-ledger.schema.json")
        duplicate_decision_schema = self.load_json(SCHEMAS / "duplicate-decision.schema.json")
        run_state_schema = self.load_json(SCHEMAS / "run-state.schema.json")
        command_event_schema = self.load_json(SCHEMAS / "command-event.schema.json")

        self.assertTrue(set(VALIDATOR.REQUIRED_TOP).issubset(findings_schema["required"]))
        finding_required = findings_schema["properties"]["findings"]["items"]["required"]
        self.assertTrue(set(VALIDATOR.REQUIRED_FINDING).issubset(finding_required))
        finding_properties = findings_schema["properties"]["findings"]["items"]["properties"]
        self.assertIn("artifact_retention", manifest_schema["required"])
        artifact_item = manifest_schema["properties"]["artifacts"]["items"]
        self.assertIn("retention", artifact_item["required"])
        self.assertEqual(["latest", "supporting", "archive"], artifact_item["properties"]["retention"]["enum"])
        self.assertEqual("^[a-f0-9]{64}$", artifact_item["properties"]["sha256"]["pattern"])
        retention_schema = manifest_schema["properties"]["artifact_retention"]
        self.assertEqual(
            {"latest_status_artifacts", "supporting_artifacts", "archive_artifacts", "by_retention", "notes"},
            set(retention_schema["required"]),
        )
        self.assertIn("taxonomies", finding_properties)
        self.assertEqual({"name", "id", "label"}, set(finding_properties["taxonomies"]["items"]["required"]))
        for field in ["bug_existence", "attacker_reachability", "boundary_crossing", "impact_assessment"]:
            self.assertEqual(
                ["Confirmed", "Probable", "Potential", "Invalid", "Not assessed"],
                finding_properties[field]["enum"],
            )
        self.assertEqual("^CHAIN-[0-9]{3,}$", finding_properties["chain_membership"]["items"]["pattern"])
        self.assertEqual("object", finding_properties["assessment_notes"]["type"])
        target_required = target_schema["properties"]["targets"]["items"]["required"]
        self.assertTrue(set(VALIDATOR.REQUIRED_TARGET).issubset(target_required))
        target_properties = target_schema["properties"]["targets"]["items"]["properties"]
        self.assertEqual("^TGT-(?:[A-Z][A-Z0-9]*-)?[0-9]{3,}$", target_properties["id"]["pattern"])
        self.assertEqual("integer", target_properties["max_files"]["type"])
        self.assertEqual(1, target_properties["max_files"]["minimum"])
        self.assertEqual(20, target_properties["max_files"]["maximum"])
        self.assertEqual(["finding-or-no-finding-with-coverage"], target_properties["expected_output"]["enum"])
        self.assertEqual(["none", "possible-link", "candidate-chain-step"], target_properties["chain_relevance"]["enum"])
        self.assertEqual("string", target_properties["security_invariants"]["items"]["type"])
        coverage_properties = target_properties["coverage"]["properties"]
        self.assertEqual(["none", "shallow", "medium", "deep"], coverage_properties["review_depth"]["enum"])
        self.assertEqual("string", coverage_properties["files_reviewed"]["items"]["type"])
        self.assertEqual("string", coverage_properties["files_skipped"]["items"]["type"])
        self.assertEqual("string", coverage_properties["commands_run"]["items"]["type"])
        self.assertEqual("string", coverage_properties["unresolved_questions"]["items"]["type"])
        self.assertEqual("boolean", coverage_properties["gapfill_recommended"]["type"])
        self.assertEqual("string", coverage_properties["gapfill_reason"]["type"])
        self.assertIn("taxonomies", target_properties)
        self.assertEqual({"name", "id", "label"}, set(target_properties["taxonomies"]["items"]["required"]))

        scanner_result = scanner_schema["properties"]["results"]["items"]
        self.assertEqual({"tool", "path", "format", "imported_at"}, set(scanner_result["required"]))
        for normalized_field in ["normalized_path", "normalized_leads_count", "normalization"]:
            self.assertIn(normalized_field, scanner_result["properties"])

        self.assertEqual(
            {
                "schema_version",
                "run_id",
                "repo",
                "commit",
                "generated_at",
                "source",
                "component_count",
                "vulnerability_count",
                "components",
                "vulnerabilities",
            },
            set(dependencies_schema["required"]),
        )
        component_schema = dependencies_schema["properties"]["components"]["items"]
        self.assertEqual(
            {"id", "name", "version", "ecosystem", "scope", "licenses", "manifest", "dependency_paths"},
            set(component_schema["required"]),
        )
        vulnerability_schema = dependencies_schema["properties"]["vulnerabilities"]["items"]
        self.assertEqual(
            {"id", "component", "severity", "fixed_version", "source", "evidence_ref", "dependency_paths"},
            set(vulnerability_schema["required"]),
        )

        self.assertEqual(
            {
                "schema_version",
                "generated_at",
                "generated_by",
                "run",
                "command",
                "paths",
                "schemas",
                "artifacts",
                "artifact_retention",
                "execution",
            },
            set(manifest_schema["required"]),
        )
        self.assertTrue({"name", "mode", "model", "effort"}.issubset(manifest_schema["properties"]["command"]["required"]))

        self.assertEqual({"run_id", "repo", "generated_at", "validations"}, set(validation_schema["required"]))
        validation_item = validation_schema["properties"]["validations"]["items"]
        self.assertEqual(
            {
                "id",
                "subject_type",
                "subject_id",
                "decision",
                "original_severity",
                "recommended_severity",
                "original_confidence",
                "recommended_confidence",
                "reasoning_summary",
                "evidence_checked",
                "missing_evidence",
                "safe_validation_steps",
            },
            set(validation_item["required"]),
        )
        validation_properties = validation_item["properties"]
        self.assertEqual("^VAL-[0-9]{3,}$", validation_properties["id"]["pattern"])
        self.assertEqual(["finding", "chain"], validation_properties["subject_type"]["enum"])
        self.assertEqual(["confirm", "downgrade", "invalidate", "needs-human-review"], validation_properties["decision"]["enum"])
        self.assertEqual(["High", "Medium", "Low", "Unknown"], validation_properties["recommended_confidence"]["enum"])

        self.assertEqual({"run_id", "repo", "commit", "generated_at", "chains"}, set(chains_schema["required"]))
        chain_item = chains_schema["properties"]["chains"]["items"]
        self.assertEqual(
            {
                "id",
                "title",
                "severity",
                "confidence",
                "status",
                "findings",
                "targets",
                "scanner_refs",
                "entry_point",
                "trust_boundaries",
                "attacker_controlled_steps",
                "required_conditions",
                "broken_security_invariants",
                "impact",
                "safe_validation_plan",
                "recommended_remediation",
            },
            set(chain_item["required"]),
        )
        chain_properties = chain_item["properties"]
        self.assertEqual("^CHAIN-[0-9]{3,}$", chain_properties["id"]["pattern"])
        self.assertEqual(["Confirmed", "Probable", "Potential", "Invalid", "Needs human review"], chain_properties["status"]["enum"])
        self.assertEqual("string", chain_properties["safe_validation_plan"]["items"]["type"])

        self.assertEqual({"run_id", "repo", "generated_at", "proofs"}, set(proofs_schema["required"]))
        proof_item = proofs_schema["properties"]["proofs"]["items"]
        self.assertEqual(
            {
                "id",
                "finding_id",
                "proof_type",
                "status",
                "safe_by_design",
                "files_created",
                "commands_run",
                "evidence",
                "limitations",
            },
            set(proof_item["required"]),
        )
        proof_properties = proof_item["properties"]
        self.assertEqual("^PROOF-[0-9]{3,}$", proof_properties["id"]["pattern"])
        self.assertEqual(
            [
                "static-trace",
                "unit-test-plan",
                "local-regression-test",
                "config-check",
                "parser-only-local-input",
                "mocked-local-service",
            ],
            proof_properties["proof_type"]["enum"],
        )
        self.assertEqual(["confirmed", "failed", "not-run", "needs-human-review"], proof_properties["status"]["enum"])
        self.assertEqual("boolean", proof_properties["safe_by_design"]["type"])
        command_item = proof_properties["commands_run"]["items"]
        self.assertEqual("object", command_item["type"])
        self.assertEqual(
            {"argv", "read_only", "writes", "network", "requires_credentials", "cwd_scope"},
            set(command_item["required"]),
        )
        self.assertEqual("array", command_item["properties"]["argv"]["type"])
        self.assertEqual("boolean", command_item["properties"]["read_only"]["type"])
        self.assertEqual("array", command_item["properties"]["writes"]["type"])
        self.assertEqual("boolean", command_item["properties"]["network"]["type"])
        self.assertEqual("boolean", command_item["properties"]["requires_credentials"]["type"])
        self.assertEqual(["run", "reports", "target_repo"], command_item["properties"]["cwd_scope"]["enum"])

        self.assertEqual({"schema_version", "run_id", "repo", "generated_at", "candidates"}, set(remediation_schema["required"]))
        remediation_item = remediation_schema["properties"]["candidates"]["items"]
        self.assertEqual(
            {
                "id",
                "finding_id",
                "status",
                "safe_by_design",
                "patch_file",
                "summary",
                "files_touched",
                "expected_validation",
                "limitations",
                "requires_human_review",
            },
            set(remediation_item["required"]),
        )
        remediation_properties = remediation_item["properties"]
        self.assertEqual("^PATCH-[0-9]{3,}$", remediation_properties["id"]["pattern"])
        self.assertEqual(["draft"], remediation_properties["status"]["enum"])
        self.assertEqual("boolean", remediation_properties["safe_by_design"]["type"])
        self.assertEqual("boolean", remediation_properties["requires_human_review"]["type"])

        self.assertEqual({"run_id", "repo", "generated_at", "traces"}, set(traces_schema["required"]))
        trace_item = traces_schema["properties"]["traces"]["items"]
        self.assertEqual(
            {
                "id",
                "finding_id",
                "producer_repo",
                "consumer_repo",
                "entry_points",
                "sink",
                "attacker_control",
                "reachable",
                "evidence",
                "limitations",
                "status",
            },
            set(trace_item["required"]),
        )
        trace_properties = trace_item["properties"]
        self.assertEqual("^TRACE-[0-9]{3,}$", trace_properties["id"]["pattern"])
        self.assertEqual(["Confirmed", "Probable", "Potential", "Invalid", "Not assessed"], trace_properties["attacker_control"]["enum"])
        self.assertEqual(["Confirmed", "Probable", "Potential", "Invalid", "Not assessed"], trace_properties["reachable"]["enum"])
        self.assertEqual(["Confirmed", "Probable", "Potential", "Invalid", "Needs human review"], trace_properties["status"]["enum"])

        self.assertEqual(
            {
                "schema_version",
                "run_id",
                "repo",
                "generated_at",
                "source",
                "safety",
                "findings",
                "adversarial_validation",
                "chains",
                "proofs",
                "gapfill",
                "traces",
                "issue_publication_plan",
                "issue_ledger",
                "duplicate_decisions",
                "observability",
                "artifacts",
                "run_duration",
            },
            set(metrics_schema["required"]),
        )
        self.assertEqual(["local-report-artifacts"], metrics_schema["properties"]["source"]["enum"])
        metrics_safety = metrics_schema["properties"]["safety"]
        self.assertEqual(
            {"local_artifacts_only", "raw_evidence_copied", "secrets_copied", "notes"},
            set(metrics_safety["required"]),
        )
        self.assertEqual("boolean", metrics_safety["properties"]["local_artifacts_only"]["type"])
        self.assertEqual("boolean", metrics_safety["properties"]["raw_evidence_copied"]["type"])
        self.assertEqual("boolean", metrics_safety["properties"]["secrets_copied"]["type"])
        artifacts_schema = metrics_schema["properties"]["artifacts"]
        self.assertTrue(
            {"manifest_by_retention", "latest_status_artifact_count", "archive_artifact_count", "manifest_hygiene_warnings"}.issubset(
                artifacts_schema["required"]
            )
        )
        gapfill_schema = metrics_schema["properties"]["gapfill"]
        self.assertTrue({"current_run", "cumulative"}.issubset(gapfill_schema["required"]))
        self.assertEqual(
            {"candidate_count", "generated_target_count", "new_target_count", "reused_target_count"},
            set(gapfill_schema["properties"]["current_run"]["required"]),
        )
        self.assertEqual(
            {"generated_target_count", "reviewed_target_count", "targets_by_status"},
            set(gapfill_schema["properties"]["cumulative"]["required"]),
        )
        self.assertEqual(
            {
                "schema_version",
                "run_id",
                "repo",
                "commit",
                "generated_at",
                "source",
                "findings",
                "warnings",
            },
            set(issue_ledger_schema["required"]),
        )
        ledger_item = issue_ledger_schema["properties"]["findings"]["items"]
        self.assertEqual(
            {
                "finding_id",
                "fingerprint",
                "publication_status",
                "issue_number",
                "state",
                "url",
                "title",
                "labels",
                "body_hash",
                "published_at",
                "source_plan",
                "plan_sha256",
                "drift",
            },
            set(ledger_item["required"]),
        )
        self.assertEqual(["not-selected", "pending", "dry-run", "published", "duplicate"], ledger_item["properties"]["publication_status"]["enum"])
        self.assertEqual(
            {
                "schema_version",
                "run_id",
                "repo",
                "commit",
                "finding_id",
                "fingerprint",
                "candidate_issue_numbers",
                "exact_match",
                "exact_match_source",
                "exact_match_url",
                "variant_of",
                "root_cause_fingerprint",
                "source_to_sink_fingerprint",
                "decision",
                "rationale",
                "checked_at",
                "source",
            },
            set(duplicate_decision_schema["required"]),
        )
        self.assertEqual(
            ["new", "exact-duplicate", "variant", "related-not-duplicate"],
            duplicate_decision_schema["properties"]["decision"]["enum"],
        )
        self.assertEqual(
            {
                "schema_version",
                "run_id",
                "repo",
                "commit",
                "generated_at",
                "source",
                "status",
                "pause_reason",
                "resume_target",
                "resume_condition",
                "paused_at",
                "paused_by",
                "final_reconcile",
                "block_reason",
                "blocked_at",
                "blocked_by",
                "resumed_at",
                "resumed_by",
            },
            set(run_state_schema["required"]),
        )
        self.assertEqual(["active", "paused", "blocked"], run_state_schema["properties"]["status"]["enum"])
        self.assertEqual(
            {
                "schema_version",
                "run_id",
                "repo",
                "command",
                "phase",
                "target_id",
                "started_at",
                "ended_at",
                "duration_ms",
                "exit_code",
                "model",
                "effort",
                "artifact_paths",
                "source",
            },
            set(command_event_schema["required"]),
        )
        self.assertEqual(
            ["gra-research", "gra-gapfill", "gra-validate-report"],
            command_event_schema["properties"]["command"]["enum"],
        )
        self.assertEqual(["genai-repo-auditor"], command_event_schema["properties"]["source"]["enum"])

    def test_valid_minimal_fixture_passes_validator(self) -> None:
        run_dir = self.copy_run()
        cp = self.run_validator(run_dir)
        self.assertEqual(cp.returncode, 0, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertIn("OK:", cp.stdout)
        self.assertIn("Findings: 1", cp.stdout)
        self.assertIn("Targets: validated", cp.stdout)

    def test_valid_scanner_index_artifacts_pass_validator(self) -> None:
        run_dir = self.copy_run()
        self.write_scanner_index(run_dir)

        cp = self.run_validator(run_dir)
        self.assertEqual(cp.returncode, 0, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertIn("Scanner index: validated", cp.stdout)

    def test_command_events_schema_and_safety_are_validated(self) -> None:
        run_dir = self.copy_run()
        events_path = run_dir / "reports" / "command-events.jsonl"
        event = {
            "schema_version": "1",
            "run_id": "fixture-run",
            "repo": "example/demo",
            "command": "gra-research",
            "phase": "exec",
            "target_id": "TGT-001",
            "started_at": "2026-05-16T00:00:00Z",
            "ended_at": "2026-05-16T00:00:02Z",
            "duration_ms": 2000,
            "exit_code": 0,
            "model": "gpt-5.5",
            "effort": "xhigh",
            "artifact_paths": ["reports/target-research/TGT-001.md"],
            "source": "genai-repo-auditor",
        }
        events_path.write_text(json.dumps(event, sort_keys=True) + "\n", encoding="utf-8")

        cp = self.run_validator(run_dir)
        self.assertEqual(cp.returncode, 0, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertIn("Command events: validated", cp.stdout)

        bad_event = dict(event)
        bad_event["ended_at"] = "2026-05-15T23:59:59Z"
        bad_event["artifact_paths"] = ["../outside.txt"]
        events_path.write_text(json.dumps(bad_event, sort_keys=True) + "\n", encoding="utf-8")
        cp_bad = self.run_validator(run_dir)
        self.assertNotEqual(cp_bad.returncode, 0)
        self.assertIn("command_events[1].ended_at: must not be earlier than started_at", cp_bad.stderr)
        self.assertIn("command_events[1].artifact_paths[0]: artifact path must not contain '..'", cp_bad.stderr)

    def test_metrics_rejects_raw_evidence_fields_and_safety_flag_drift(self) -> None:
        run_dir = self.copy_run()
        metrics = {
            "schema_version": "1",
            "run_id": "fixture-run",
            "repo": "example/demo",
            "generated_at": "2026-05-28T00:00:00Z",
            "source": "local-report-artifacts",
            "safety": {
                "local_artifacts_only": True,
                "raw_evidence_copied": False,
                "secrets_copied": True,
                "notes": "fixture",
            },
            "findings": {
                "total": 1,
                "by_severity": {"High": 1},
                "by_status": {"Confirmed": 1},
                "issue_recommended": 1,
                "chain_membership_count": 0,
            },
            "adversarial_validation": {
                "artifact_present": False,
                "total": 0,
                "by_decision": {},
                "downgrade_or_invalidate_count": 0,
                "downgrade_or_invalidate_rate": 0,
                "blocking_decision_count": 0,
            },
            "chains": {"artifact_present": False, "total": 0, "by_status": {}, "by_severity": {}},
            "proofs": {"artifact_present": False, "total": 0, "by_type": {}, "by_status": {}},
            "gapfill": {
                "coverage_artifact_present": False,
                "gapfill_artifact_present": False,
                "source_targets_recommended": 0,
                "current_run": {
                    "candidate_count": 0,
                    "generated_target_count": 0,
                    "new_target_count": 0,
                    "reused_target_count": 0,
                },
                "cumulative": {
                    "generated_target_count": 0,
                    "reviewed_target_count": 0,
                    "targets_by_status": {},
                },
                "targets_generated": 0,
                "targets_reviewed": 0,
                "targets_by_status": {},
            },
            "traces": {
                "artifact_present": False,
                "total": 0,
                "by_reachable": {},
                "by_attacker_control": {},
                "by_status": {},
            },
            "issue_publication_plan": {"artifact_present": False, "selected_findings": 0, "warning_count": 0},
            "issue_ledger": {
                "artifact_present": False,
                "tracked_findings": 0,
                "published_findings": 0,
                "by_publication_status": {},
                "drift_warning_count": 0,
            },
            "duplicate_decisions": {
                "artifact_present": False,
                "total": 0,
                "by_decision": {},
                "exact_match_count": 0,
                "candidate_issue_count": 0,
            },
            "observability": {
                "command_events_present": False,
                "total_events": 0,
                "by_command": {},
                "by_phase": {},
                "by_exit_code": {},
                "execution_durations": [],
                "failures_by_target": {},
                "reruns_by_target": {},
                "events_by_target": {},
                "validation_retry_count": 0,
                "validation_retries_by_target": {},
                "taxonomy_normalizations_present": False,
                "taxonomy_normalization_count": 0,
                "taxonomy_normalizations_by_target": {},
            },
            "artifacts": {
                "manifest_present": False,
                "manifest_artifact_total": 0,
                "manifest_by_kind": {},
                "manifest_by_retention": {},
                "latest_status_artifact_count": 0,
                "archive_artifact_count": 0,
                "manifest_hygiene_warnings": 0,
                "reports_file_count": 2,
                "reports_dir_count": 0,
            },
            "run_duration": {"available": False, "seconds": None, "source": "not-available"},
            "evidence": "raw evidence must never be present in metrics",
        }
        self.write_json(run_dir / "reports" / "metrics.json", metrics)

        cp = self.run_validator(run_dir)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("metrics.safety.secrets_copied: must be false", cp.stderr)
        self.assertIn("metrics.evidence: metrics must not copy raw evidence or issue body content", cp.stderr)

    def test_scanner_index_rejects_unsafe_artifact_paths(self) -> None:
        run_dir = self.copy_run()
        self.write_scanner_index(
            run_dir,
            entry_overrides={
                "path": "../scanner.json",
                "normalized_path": "reports/scanner-results/../normalized/semgrep-leads.json",
            },
        )

        cp = self.run_validator(run_dir)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("scanner_index.results[0].path: scanner artifact path must not contain '..'", cp.stderr)
        self.assertIn("scanner_index.results[0].normalized_path: scanner artifact path must not contain '..'", cp.stderr)

    def test_scanner_index_rejects_missing_normalized_artifact(self) -> None:
        run_dir = self.copy_run()
        self.write_scanner_index(run_dir, entry_overrides={"normalized_path": "reports/scanner-results/normalized/missing-leads.json"})

        cp = self.run_validator(run_dir)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("scanner_index.results[0].normalized_path: normalized scanner artifact not found", cp.stderr)

    def test_scanner_index_rejects_missing_normalized_metadata_fields(self) -> None:
        run_dir = self.copy_run()
        scanner_index = self.write_scanner_index(run_dir)
        scanner_index["results"][0].pop("normalized_leads_count")
        scanner_index["results"][0].pop("normalization")
        self.write_json(run_dir / "reports" / "scanner-results" / "scanner-index.json", scanner_index)

        cp = self.run_validator(run_dir)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("scanner_index.results[0].normalized_leads_count: missing normalized lead count", cp.stderr)
        self.assertIn("scanner_index.results[0].normalization: missing normalization metadata", cp.stderr)

    def test_scanner_index_rejects_symlinked_scanner_results_parent(self) -> None:
        run_dir = self.copy_run()
        outside_scanner = self.work_dir / "outside-scanner-results"
        outside_normalized = outside_scanner / "normalized"
        outside_normalized.mkdir(parents=True)
        (outside_scanner / "semgrep.json").write_text('{"results": []}\n', encoding="utf-8")
        self.write_json(
            outside_normalized / "semgrep-leads.json",
            {
                "tool": "semgrep",
                "raw_result_ref": "reports/scanner-results/semgrep.json",
                "raw_bytes": 16,
                "format": "json",
                "normalization": {"parse_error": "", "results_truncated": False},
                "leads": [{"rule_id": "fixture.rule", "raw_result_ref": "reports/scanner-results/semgrep.json"}],
            },
        )
        self.write_json(
            outside_scanner / "scanner-index.json",
            {
                "run_id": "fixture-run",
                "repo": "example/demo",
                "generated_at": "2026-05-16T00:00:00Z",
                "results": [
                    {
                        "tool": "semgrep",
                        "path": "reports/scanner-results/semgrep.json",
                        "format": "json",
                        "imported_at": "2026-05-16T00:00:01Z",
                        "raw_bytes": 16,
                        "normalized_path": "reports/scanner-results/normalized/semgrep-leads.json",
                        "normalized_leads_count": 1,
                        "normalization": {"parse_error": "", "results_truncated": False},
                    }
                ],
            },
        )
        (run_dir / "reports" / "scanner-results").symlink_to(outside_scanner, target_is_directory=True)

        cp = self.run_validator(run_dir)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("scanner_index: scanner artifact path must not contain symlink components", cp.stderr)

    def test_scanner_index_rejects_malformed_counts_and_metadata_drift(self) -> None:
        run_dir = self.copy_run()
        self.write_scanner_index(
            run_dir,
            leads=[
                {"rule_id": "fixture.one", "raw_result_ref": "reports/scanner-results/semgrep.json"},
                {"rule_id": "fixture.two", "raw_result_ref": "reports/scanner-results/semgrep.json"},
            ],
            entry_overrides={
                "raw_bytes": 999,
                "normalized_leads_count": 1,
                "normalization": {"parse_error": "drift"},
            },
        )

        cp = self.run_validator(run_dir)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("normalized_leads_count: value 1 does not match normalized leads length 2", cp.stderr)
        self.assertIn("normalization: value does not match normalized artifact metadata", cp.stderr)
        self.assertIn("raw_bytes: value does not match normalized artifact raw_bytes", cp.stderr)

    def test_missing_required_fields_fail_with_actionable_messages(self) -> None:
        run_dir = self.copy_run()
        findings_path = run_dir / "reports" / "findings.json"
        findings = self.load_json(findings_path)
        findings.pop("commit")
        findings["findings"][0].pop("evidence")
        self.write_json(findings_path, findings)

        cp = self.run_validator(run_dir)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("findings.commit", cp.stderr)
        self.assertIn("findings.findings[0].evidence: missing", cp.stderr)
        self.assertIn("Validation failed", cp.stderr)

    def test_invalid_enum_values_fail_validation(self) -> None:
        run_dir = self.copy_run()
        findings_path = run_dir / "reports" / "findings.json"
        findings = self.load_json(findings_path)
        findings["findings"][0]["severity"] = "Urgent"
        findings["findings"][0]["status"] = "Triaged"
        findings["findings"][0]["public_disclosure_risk"] = "Extreme"
        self.write_json(findings_path, findings)

        targets_path = run_dir / "reports" / "targets.json"
        targets = self.load_json(targets_path)
        targets["targets"][0]["risk"] = "urgent"
        targets["targets"][0]["recommended_mode"] = "interactive"
        self.write_json(targets_path, targets)

        cp = self.run_validator(run_dir)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("findings.findings[0].severity: value 'Urgent' is not one of", cp.stderr)
        self.assertIn("findings.findings[0].status: value 'Triaged' is not one of", cp.stderr)
        self.assertIn("public_disclosure_risk", cp.stderr)
        self.assertIn("targets.targets[0].risk", cp.stderr)
        self.assertIn("targets.targets[0].recommended_mode", cp.stderr)

    def test_unsafe_paths_and_issue_body_references_fail_validation(self) -> None:
        run_dir = self.copy_run()
        findings_path = run_dir / "reports" / "findings.json"
        findings = self.load_json(findings_path)
        finding = findings["findings"][0]
        finding["affected_locations"][0]["file"] = "../secret.py"
        finding["issue_body_file"] = "reports/issue-drafts/../secret.md"
        self.write_json(findings_path, findings)

        cp = self.run_validator(run_dir)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("affected_locations[0].file", cp.stderr)
        self.assertIn("issue_body_file must not contain", cp.stderr)

    def test_run_manifest_retention_hygiene_validates_latest_and_archive_artifacts(self) -> None:
        run_dir = self.copy_run()
        (run_dir / "run-summary.txt").write_text("final_status=0\n", encoding="utf-8")
        (run_dir / "report-validation.txt").write_text("OK\n", encoding="utf-8")
        (run_dir / "codex-transcript.txt").write_text("intermediate transcript\n", encoding="utf-8")
        target_research = run_dir / "reports" / "target-research"
        target_research.mkdir(parents=True, exist_ok=True)
        (target_research / "TGT-001.md").write_text("not json, retained for reproducibility\n", encoding="utf-8")

        manifest = self.write_run_manifest(run_dir)
        latest = manifest["artifact_retention"]["latest_status_artifacts"]
        archive = manifest["artifact_retention"]["archive_artifacts"]
        self.assertIn("reports/findings.json", latest)
        self.assertIn("reports/targets.json", latest)
        self.assertIn("run-summary.txt", latest)
        self.assertIn("report-validation.txt", latest)
        self.assertIn("codex-transcript.txt", archive)
        self.assertIn("reports/target-research", archive)
        findings_entry = next(item for item in manifest["artifacts"] if item["path"] == "reports/findings.json")
        self.assertEqual("latest", findings_entry["retention"])
        self.assertRegex(findings_entry["sha256"], r"^[a-f0-9]{64}$")
        transcript_entry = next(item for item in manifest["artifacts"] if item["path"] == "codex-transcript.txt")
        self.assertEqual("archive", transcript_entry["retention"])

        cp = self.run_validator(run_dir)
        self.assertEqual(cp.returncode, 0, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertIn("Run manifest: validated", cp.stdout)

    def test_run_manifest_hygiene_rejects_stale_retention_and_digest(self) -> None:
        run_dir = self.copy_run()
        (run_dir / "run-summary.txt").write_text("final_status=0\n", encoding="utf-8")
        (run_dir / "report-validation.txt").write_text("OK\n", encoding="utf-8")
        manifest = self.write_run_manifest(run_dir)
        for artifact in manifest["artifacts"]:
            if artifact.get("path") == "reports/findings.json":
                artifact["retention"] = "archive"
                artifact["sha256"] = "0" * 64
                break
        manifest["artifact_retention"]["latest_status_artifacts"] = [
            path for path in manifest["artifact_retention"]["latest_status_artifacts"] if path != "reports/targets.json"
        ]
        manifest["artifact_retention"]["by_retention"]["latest"] = 999
        self.write_json(run_dir / "run-manifest.json", manifest)

        cp = self.run_validator(run_dir)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("run_manifest.artifacts", cp.stderr)
        self.assertIn("sha256: value does not match file digest", cp.stderr)
        self.assertIn("reports/findings.json must have retention 'latest'", cp.stderr)
        self.assertIn("missing latest artifact from summary: reports/targets.json", cp.stderr)
        self.assertIn("artifact_retention.by_retention.latest", cp.stderr)

    def test_scanner_index_schema_accepts_normalized_artifact_fields(self) -> None:
        scanner_index = {
            "run_id": "fixture-run",
            "repo": "example/demo",
            "generated_at": "2026-05-16T00:00:00Z",
            "results": [
                {
                    "tool": "semgrep",
                    "path": "reports/scanner-results/semgrep.json",
                    "format": "json",
                    "imported_at": "2026-05-16T00:00:01Z",
                    "sha256": "abc123",
                    "raw_bytes": 42,
                    "normalized_path": "reports/scanner-results/normalized/semgrep-leads.json",
                    "normalized_leads_count": 1,
                    "normalization": {"parse_error": "", "results_truncated": False},
                    "note": "fixture",
                }
            ],
        }
        errors: list[str] = []
        VALIDATOR.validate_schema(scanner_index, VALIDATOR.load_schema("scanner-index.schema.json"), "scanner_index", errors)
        self.assertEqual([], errors)

        invalid = json.loads(json.dumps(scanner_index))
        invalid["results"][0].pop("path")
        invalid["results"][0]["raw_bytes"] = -1
        invalid["results"][0]["normalized_leads_count"] = -1
        errors = []
        VALIDATOR.validate_schema(invalid, VALIDATOR.load_schema("scanner-index.schema.json"), "scanner_index", errors)
        joined = "\n".join(errors)
        self.assertIn("scanner_index.results[0].path: missing required field", joined)
        self.assertIn("scanner_index.results[0].raw_bytes: value -1 is below minimum 0", joined)
        self.assertIn("scanner_index.results[0].normalized_leads_count: value -1 is below minimum 0", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
