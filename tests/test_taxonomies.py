from __future__ import annotations

import contextlib
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"

sys.path.insert(0, str(REPO_ROOT / "lib"))
from taxonomies import (  # noqa: E402
    TaxonomyAliasError,
    load_taxonomy_aliases,
    load_taxonomy_profiles,
    normalize_taxonomy_refs,
    suggest_taxonomy_replacement,
    taxonomy_label_map,
    validate_taxonomy_refs,
    TaxonomyProfileError,
)
from gralib import ensure_taxonomy_templates  # noqa: E402
from target_queue import target_fingerprint, validate_target_queue_artifact  # noqa: E402


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

    def run_cmd(self, *args: str | Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(arg) for arg in args],
            cwd=REPO_ROOT,
            env=env,
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

    def test_run_directories_receive_taxonomy_profiles_and_aliases(self) -> None:
        run_dir = self.work_dir / "run"
        ensure_taxonomy_templates(REPO_ROOT, run_dir)
        self.assertTrue((run_dir / "templates" / "taxonomies" / "cwe-subset.json").exists())
        self.assertTrue((run_dir / "templates" / "taxonomy-aliases.json").exists())

    def test_taxonomy_profile_loader_rejects_malformed_and_duplicate_profiles(self) -> None:
        malformed_dir = self.work_dir / "malformed-taxonomies"
        malformed_dir.mkdir()
        (malformed_dir / "bad.json").write_text('{"name": "Broken", "entries": [', encoding="utf-8")
        with self.assertRaisesRegex(TaxonomyProfileError, "invalid taxonomy JSON"):
            load_taxonomy_profiles(malformed_dir)

        duplicate_dir = self.work_dir / "duplicate-taxonomies"
        duplicate_dir.mkdir()
        profile = {"name": "Duplicate Taxonomy", "entries": [{"id": "DUP-1", "label": "Duplicate"}]}
        self.write_json(duplicate_dir / "a.json", profile)
        self.write_json(duplicate_dir / "b.json", profile)
        with self.assertRaisesRegex(TaxonomyProfileError, "duplicate taxonomy profile name"):
            load_taxonomy_profiles(duplicate_dir)

    def test_taxonomy_alias_loader_rejects_malformed_aliases(self) -> None:
        malformed = self.work_dir / "bad-aliases.json"
        malformed.write_text('{"name_aliases": "CWE"}\n', encoding="utf-8")
        with self.assertRaisesRegex(TaxonomyAliasError, "name_aliases must be a list"):
            load_taxonomy_aliases(malformed)
        malformed_mapping = self.work_dir / "bad-id-mapping.json"
        self.write_json(
            malformed_mapping,
            {"name_aliases": [], "id_mappings": [{"from": {"name": "CWE"}, "to": {"name": "CWE Subset"}}]},
        )
        with self.assertRaisesRegex(TaxonomyAliasError, "id_mappings\\[0\\].from.id"):
            load_taxonomy_aliases(malformed_mapping)
        duplicate_name = self.work_dir / "duplicate-name-alias.json"
        self.write_json(
            duplicate_name,
            {
                "name_aliases": [
                    {"from": "CWE", "to": "CWE Subset"},
                    {"from": "CWE", "to": "Other CWE"},
                ],
                "id_mappings": [],
            },
        )
        with self.assertRaisesRegex(TaxonomyAliasError, "duplicate alias 'CWE'"):
            load_taxonomy_aliases(duplicate_name)
        duplicate_mapping = self.work_dir / "duplicate-id-mapping.json"
        self.write_json(
            duplicate_mapping,
            {
                "name_aliases": [],
                "id_mappings": [
                    {
                        "from": {"name": "CWE Subset", "id": "CWE-284"},
                        "to": {"name": "CWE Subset", "id": "CWE-862"},
                    },
                    {
                        "from": {"name": "CWE Subset", "id": "CWE-284"},
                        "to": {"name": "CWE Subset", "id": "CWE-863"},
                    },
                ],
            },
        )
        with self.assertRaisesRegex(TaxonomyAliasError, "duplicate mapping 'CWE Subset':'CWE-284'"):
            load_taxonomy_aliases(duplicate_mapping)

    def test_validate_report_reports_malformed_taxonomy_profiles_without_traceback(self) -> None:
        run_dir = self.copy_run()
        taxonomy_dir = self.work_dir / "bad-taxonomies"
        taxonomy_dir.mkdir()
        (taxonomy_dir / "bad.json").write_text('{"name": "Broken", "entries": [', encoding="utf-8")
        env = os.environ.copy()
        env["GENAI_REPO_AUDITOR_TAXONOMY_DIR"] = str(taxonomy_dir)

        cp = self.run_cmd(REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir, env=env)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("taxonomy profiles/aliases:", cp.stderr)
        self.assertIn("invalid taxonomy JSON", cp.stderr)
        self.assertNotIn("Traceback", cp.stderr)

    def test_validate_taxonomy_refs_requires_label_without_schema_precheck(self) -> None:
        profiles = load_taxonomy_profiles()
        labels = taxonomy_label_map(profiles)
        errors: list[str] = []
        validate_taxonomy_refs(
            [{"name": "OWASP LLM Top 10 2025", "id": "LLM01"}],
            "findings.findings[0].taxonomies",
            errors,
            profiles,
            labels,
        )
        self.assertEqual(
            ["findings.findings[0].taxonomies[0].label: taxonomy label must be non-empty string"],
            errors,
        )

    def test_taxonomy_preflight_normalizes_known_aliases_and_labels(self) -> None:
        profiles = load_taxonomy_profiles()
        labels = taxonomy_label_map(profiles)
        refs = [
            {"name": "CWE", "id": "CWE-284", "label": "Improper Access Control"},
            {"name": "CWE Subset", "id": "CWE-94", "label": "Improper Control of Generation of Code"},
        ]
        normalized, changes, errors = normalize_taxonomy_refs(
            refs,
            "findings.findings[0].taxonomies",
            profiles,
            labels,
            load_taxonomy_aliases(),
        )
        self.assertEqual([], errors)
        self.assertEqual(
            [
                {"name": "CWE Subset", "id": "CWE-862", "label": "Missing Authorization"},
                {"name": "CWE Subset", "id": "CWE-94", "label": "Code Injection"},
            ],
            normalized,
        )
        self.assertEqual(2, len(changes))
        self.assertEqual("findings.findings[0].taxonomies[0]", changes[0]["field_path"])
        self.assertIn("CWE-284", json.dumps(changes[0]["before"]))
        self.assertIn("CWE-862", json.dumps(changes[0]["after"]))

    def test_validate_taxonomy_refs_suggests_configured_replacements(self) -> None:
        profiles = load_taxonomy_profiles()
        labels = taxonomy_label_map(profiles)
        suggestion = suggest_taxonomy_replacement("CWE Subset", "CWE-266", profiles, labels, load_taxonomy_aliases())
        self.assertIsNotNone(suggestion)
        self.assertEqual("CWE-269", suggestion["id"])
        self.assertEqual("suggest", suggestion["mode"])
        errors: list[str] = []
        validate_taxonomy_refs(
            [{"name": "CWE Subset", "id": "CWE-266", "label": "Incorrect Privilege Assignment"}],
            "findings.findings[0].taxonomies",
            errors,
            profiles,
            labels,
            load_taxonomy_aliases(),
        )
        self.assertEqual(1, len(errors))
        self.assertIn("unknown id 'CWE-266'", errors[0])
        self.assertIn("suggested replacement CWE Subset:CWE-269", errors[0])

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

    def test_taxonomy_preflight_cli_fixes_fixture_before_validation(self) -> None:
        run_dir = self.copy_run()
        self.add_taxonomies(run_dir)
        findings_path = run_dir / "reports" / "findings.json"
        findings = self.load_json(findings_path)
        findings["findings"][0]["taxonomies"][0] = {
            "name": "CWE",
            "id": "CWE-284",
            "label": "Improper Access Control",
        }
        findings["findings"][0]["taxonomies"][1]["label"] = "Wrong label"
        self.write_json(findings_path, findings)

        before = self.run_cmd(REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir)
        self.assertNotEqual(before.returncode, 0)
        self.assertIn("suggested replacement CWE Subset:CWE-862", before.stderr)

        fix = self.run_cmd(REPO_ROOT / "bin" / "gra-taxonomy-preflight", "--run", run_dir, "--fix")
        self.assertEqual(fix.returncode, 0, f"stdout:\n{fix.stdout}\nstderr:\n{fix.stderr}")
        updated = self.load_json(findings_path)
        self.assertEqual(
            {"name": "CWE Subset", "id": "CWE-862", "label": "Missing Authorization"},
            updated["findings"][0]["taxonomies"][0],
        )
        self.assertEqual(
            {"name": "OWASP LLM Top 10 2025", "id": "LLM01", "label": "Prompt Injection"},
            updated["findings"][0]["taxonomies"][1],
        )
        log_path = run_dir / "reports" / "taxonomy-normalizations.jsonl"
        self.assertTrue(log_path.exists())
        log_lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        self.assertGreaterEqual(len(log_lines), 2)
        self.assertEqual("gra-taxonomy-preflight", log_lines[0]["source"])
        self.assertIn("before", log_lines[0])
        self.assertIn("after", log_lines[0])

        after = self.run_cmd(REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir)
        self.assertEqual(after.returncode, 0, f"stdout:\n{after.stdout}\nstderr:\n{after.stderr}")

    def test_taxonomy_preflight_refreshes_managed_queue_fingerprints(self) -> None:
        run_dir = self.copy_run()
        targets_path = run_dir / "reports" / "targets.json"
        targets = self.load_json(targets_path)
        targets["targets"][0]["taxonomies"] = [
            {"name": "CWE", "id": "CWE-284", "label": "Improper Access Control"}
        ]
        deferred_seed = copy.deepcopy(targets["targets"][0])
        deferred_seed.update(
            {
                "id": "TGT-002",
                "priority": 70,
                "scope": "deferred.py",
                "entry_points": ["tests.fixture.deferred"],
            }
        )
        targets["targets"].append(deferred_seed)
        self.write_json(targets_path, targets)

        queued = self.run_cmd(
            REPO_ROOT / "bin" / "gra-targets", "--run", run_dir, "--rebalance", "--target-budget", "1"
        )
        self.assertEqual(queued.returncode, 0, f"stdout:\n{queued.stdout}\nstderr:\n{queued.stderr}")
        before = self.load_json(targets_path)
        before_fingerprint = before["targets"][0]["queue_fingerprint"]

        fixed = self.run_cmd(REPO_ROOT / "bin" / "gra-taxonomy-preflight", "--run", run_dir, "--fix")
        self.assertEqual(fixed.returncode, 0, f"stdout:\n{fixed.stdout}\nstderr:\n{fixed.stderr}")
        after = self.load_json(targets_path)
        target = after["targets"][0]
        self.assertEqual(
            [{"name": "CWE Subset", "id": "CWE-862", "label": "Missing Authorization"}],
            target["taxonomies"],
        )
        self.assertNotEqual(before_fingerprint, target["queue_fingerprint"])
        self.assertEqual(target_fingerprint(target), target["queue_fingerprint"])
        self.assertEqual(target["queue_fingerprint"], after["queue_summary"]["decisions"][0]["fingerprint"])
        self.assertEqual(
            [{"name": "CWE Subset", "id": "CWE-862", "label": "Missing Authorization"}],
            after["deferred_targets"][0]["taxonomies"],
        )
        self.assertEqual([], validate_target_queue_artifact(after))

        repeat = self.run_cmd(REPO_ROOT / "bin" / "gra-taxonomy-preflight", "--run", run_dir, "--fix")
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertEqual(after, self.load_json(targets_path))

    def test_taxonomy_preflight_cli_rejects_missing_explicit_findings_path(self) -> None:
        missing = self.work_dir / "missing-findings.json"
        cp = self.run_cmd(REPO_ROOT / "bin" / "gra-taxonomy-preflight", "--findings", missing)
        self.assertEqual(cp.returncode, 1)
        self.assertIn("artifact not found", cp.stderr)

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
