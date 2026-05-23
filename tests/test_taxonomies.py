from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"

sys.path.insert(0, str(REPO_ROOT / "lib"))
from taxonomies import load_taxonomy_profiles, taxonomy_label_map  # noqa: E402


class TaxonomyTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def copy_run(self) -> Path:
        dst = self.work_dir / "minimal-run"
        shutil.copytree(FIXTURES / "minimal-run", dst)
        return dst

    def load_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def run_cmd(self, *args: str | Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(arg) for arg in args],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def add_taxonomies(self, run_dir: Path) -> None:
        findings_path = run_dir / "reports" / "findings.json"
        findings = self.load_json(findings_path)
        findings["findings"][0]["taxonomies"] = [
            {"name": "CWE Subset", "id": "CWE-78", "label": "OS Command Injection"},
            {"name": "OWASP LLM Top 10 2025", "id": "LLM01", "label": "Prompt Injection"},
        ]
        findings["findings"][0]["cwe"] = ["CWE-78"]
        self.write_json(findings_path, findings)

        targets_path = run_dir / "reports" / "targets.json"
        targets = self.load_json(targets_path)
        targets["targets"][0]["taxonomies"] = [
            {"name": "Supply Chain Posture", "id": "SC-CICD-TOKEN-PERMISSIONS", "label": "CI/CD Token Permissions"}
        ]
        self.write_json(targets_path, targets)

    def test_taxonomy_profiles_are_machine_readable(self) -> None:
        profiles = load_taxonomy_profiles()
        self.assertIn("OWASP LLM Top 10 2025", profiles)
        self.assertIn("OWASP AI Agent Security", profiles)
        self.assertIn("MCP Security", profiles)
        self.assertIn("Supply Chain Posture", profiles)
        self.assertIn("CWE Subset", profiles)
        labels = taxonomy_label_map(profiles)
        self.assertEqual(labels[("OWASP LLM Top 10 2025", "LLM01")], "Prompt Injection")
        self.assertEqual(labels[("MCP Security", "MCP-TOKEN-PASSTHROUGH")], "Token Passthrough")

    def test_validate_report_accepts_controlled_taxonomy_ids(self) -> None:
        run_dir = self.copy_run()
        self.add_taxonomies(run_dir)
        cp = self.run_cmd(REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir)
        self.assertEqual(cp.returncode, 0, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")

    def test_validate_report_rejects_unknown_taxonomy_id_and_label_drift(self) -> None:
        run_dir = self.copy_run()
        self.add_taxonomies(run_dir)
        findings_path = run_dir / "reports" / "findings.json"
        findings = self.load_json(findings_path)
        findings["findings"][0]["taxonomies"][0]["id"] = "CWE-999999"
        findings["findings"][0]["taxonomies"][1]["label"] = "Wrong label"
        self.write_json(findings_path, findings)
        cp = self.run_cmd(REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("unknown id 'CWE-999999'", cp.stderr)
        self.assertIn("does not match taxonomy label 'Prompt Injection'", cp.stderr)

    def test_dashboard_and_sarif_include_taxonomy_metadata(self) -> None:
        run_dir = self.copy_run()
        self.add_taxonomies(run_dir)
        cp_dashboard = self.run_cmd(REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir)
        self.assertEqual(cp_dashboard.returncode, 0, cp_dashboard.stderr)
        dashboard = (run_dir / "reports" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Taxonomies", dashboard)
        self.assertIn("OWASP LLM Top 10 2025", dashboard)
        self.assertIn("SC-CICD-TOKEN-PERMISSIONS", dashboard)

        cp_sarif = self.run_cmd(REPO_ROOT / "bin" / "gra-sarif", "--run", run_dir)
        self.assertEqual(cp_sarif.returncode, 0, cp_sarif.stderr)
        sarif = self.load_json(run_dir / "reports" / "findings.sarif")
        rule_props = sarif["runs"][0]["tool"]["driver"]["rules"][0]["properties"]
        self.assertIn("CWE-78", rule_props["cwe"])
        self.assertIn("OWASP LLM Top 10 2025:LLM01", rule_props["tags"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
