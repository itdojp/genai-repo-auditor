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

        self.assertTrue(set(VALIDATOR.REQUIRED_TOP).issubset(findings_schema["required"]))
        finding_required = findings_schema["properties"]["findings"]["items"]["required"]
        self.assertTrue(set(VALIDATOR.REQUIRED_FINDING).issubset(finding_required))
        target_required = target_schema["properties"]["targets"]["items"]["required"]
        self.assertTrue(set(VALIDATOR.REQUIRED_TARGET).issubset(target_required))

        scanner_result = scanner_schema["properties"]["results"]["items"]
        self.assertEqual(["tool", "path", "format", "imported_at"], scanner_result["required"])
        for normalized_field in ["normalized_path", "normalized_leads_count", "normalization"]:
            self.assertIn(normalized_field, scanner_result["properties"])

    def test_valid_minimal_fixture_passes_validator(self) -> None:
        run_dir = self.copy_run()
        cp = self.run_validator(run_dir)
        self.assertEqual(cp.returncode, 0, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        self.assertIn("OK:", cp.stdout)
        self.assertIn("Findings: 1", cp.stdout)
        self.assertIn("Targets: validated", cp.stdout)

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
