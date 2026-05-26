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

        self.assertTrue(set(VALIDATOR.REQUIRED_TOP).issubset(findings_schema["required"]))
        finding_required = findings_schema["properties"]["findings"]["items"]["required"]
        self.assertTrue(set(VALIDATOR.REQUIRED_FINDING).issubset(finding_required))
        finding_properties = findings_schema["properties"]["findings"]["items"]["properties"]
        self.assertIn("taxonomies", finding_properties)
        self.assertEqual({"name", "id", "label"}, set(finding_properties["taxonomies"]["items"]["required"]))
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
                "execution",
            },
            set(manifest_schema["required"]),
        )
        self.assertTrue({"name", "mode", "model", "effort"}.issubset(manifest_schema["properties"]["command"]["required"]))

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
