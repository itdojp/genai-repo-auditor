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
from dependency_posture import analyze_dependencies, append_dependency_posture_targets, should_ingest_dependencies, write_dependency_artifacts  # noqa: E402


class DependencyIngestionTests(unittest.TestCase):
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
        run_dir = self.work_dir / "run"
        shutil.copytree(FIXTURES / "minimal-run", run_dir)
        return run_dir

    def test_cyclonedx_fixture_preserves_paths_and_vulnerabilities(self) -> None:
        run_dir = self.copy_run()
        data = analyze_dependencies(
            run_dir=run_dir,
            raw_path=FIXTURES / "sbom" / "cyclonedx.json",
            raw_result_ref="reports/scanner-results/sbom-cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )

        self.assertEqual("cyclonedx", data["source"]["detected_format"])
        self.assertEqual("vulnerabilities_observed", data["status"])
        components = {component["id"]: component for component in data["components"]}
        self.assertEqual(["pkg:github/example/demo@0.1.0"], components["pkg:github/example/demo@0.1.0"]["dependency_paths"][0])
        self.assertEqual("direct", components["pkg:pypi/lib-a@1.0.0"]["scope"])
        self.assertEqual("transitive", components["pkg:pypi/lib-b@2.0.0"]["scope"])
        self.assertEqual(["MIT"], components["pkg:pypi/lib-a@1.0.0"]["licenses"])
        vuln = data["vulnerabilities"][0]
        self.assertEqual("GHSA-demo-0001", vuln["id"])
        self.assertEqual("High", vuln["severity"])
        self.assertEqual("2.0.1", vuln["fixed_version"])
        self.assertEqual(["pkg:github/example/demo@0.1.0", "pkg:pypi/lib-a@1.0.0", "pkg:pypi/lib-b@2.0.0"], vuln["dependency_paths"][0])

    def test_cyclonedx_unknown_vulnerability_component_remains_valid_evidence(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "partial-cyclonedx.json"
        partial_sbom = json.loads((FIXTURES / "sbom" / "cyclonedx.json").read_text(encoding="utf-8"))
        partial_sbom["vulnerabilities"][0]["affects"][0]["ref"] = "missing-component-ref"
        raw_path.write_text(json.dumps(partial_sbom, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        data = write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/partial-cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )

        self.assertEqual("", data["vulnerabilities"][0]["component"])
        self.assertEqual("missing-component-ref", data["vulnerabilities"][0]["evidence_ref"])
        validation = subprocess.run(
            [sys.executable, REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, validation.returncode, f"stdout:\n{validation.stdout}\nstderr:\n{validation.stderr}")
        self.assertIn("Dependencies: validated", validation.stdout)

    def test_spdx_fixture_preserves_direct_transitive_and_security_refs(self) -> None:
        run_dir = self.copy_run()
        data = analyze_dependencies(
            run_dir=run_dir,
            raw_path=FIXTURES / "sbom" / "spdx.json",
            raw_result_ref="reports/scanner-results/sbom-spdx.json",
            tool="sbom",
            requested_format="spdx",
        )

        self.assertEqual("spdx", data["source"]["detected_format"])
        components = {component["id"]: component for component in data["components"]}
        self.assertEqual("direct", components["pkg:npm/left-pad@1.3.0"]["scope"])
        self.assertEqual("transitive", components["pkg:npm/ansi-wrap@0.1.0"]["scope"])
        vuln = data["vulnerabilities"][0]
        self.assertEqual("GHSA-spdx-0001", vuln["id"])
        self.assertEqual("Medium", vuln["severity"])
        self.assertEqual("1.3.1", vuln["fixed_version"])

    def test_github_dependency_graph_sbom_wrapper_is_accepted(self) -> None:
        run_dir = self.copy_run()
        data = analyze_dependencies(
            run_dir=run_dir,
            raw_path=FIXTURES / "sbom" / "github-sbom.json",
            raw_result_ref="reports/scanner-results/github-sbom.json",
            tool="sbom",
            requested_format="auto",
        )

        self.assertEqual("github-spdx", data["source"]["detected_format"])
        components = {component["id"]: component for component in data["components"]}
        self.assertEqual("direct", components["pkg:gem/rails@7.0.0"]["scope"])
        self.assertEqual(0, data["vulnerability_count"])

    def test_syft_fixture_preserves_direct_and_transitive_paths(self) -> None:
        run_dir = self.copy_run()
        data = analyze_dependencies(
            run_dir=run_dir,
            raw_path=FIXTURES / "sbom" / "syft.json",
            raw_result_ref="reports/scanner-results/syft.json",
            tool="sbom",
            requested_format="syft",
        )

        self.assertEqual("syft", data["source"]["detected_format"])
        components = {component["id"]: component for component in data["components"]}
        self.assertEqual("direct", components["pkg:npm/direct-lib@1.2.3"]["scope"])
        self.assertEqual("transitive", components["pkg:npm/transitive-lib@4.5.6"]["scope"])
        self.assertEqual(["MIT"], components["pkg:npm/direct-lib@1.2.3"]["licenses"])
        self.assertEqual(
            ["pkg:generic/demo-app@0.1.0", "pkg:npm/direct-lib@1.2.3", "pkg:npm/transitive-lib@4.5.6"],
            components["pkg:npm/transitive-lib@4.5.6"]["dependency_paths"][0],
        )

    def test_trivy_sbom_format_alias_triggers_dependency_ingestion(self) -> None:
        self.assertTrue(should_ingest_dependencies(safe_tool="trivy", fmt="cyclonedx"))
        self.assertTrue(should_ingest_dependencies(safe_tool="trivy", fmt="spdx"))
        self.assertFalse(should_ingest_dependencies(safe_tool="trivy", fmt="json"))

    def test_gra_ingest_writes_dependency_artifacts_dashboard_and_validates(self) -> None:
        run_dir = self.copy_run()
        sbom_path = FIXTURES / "sbom" / "cyclonedx.json"

        ingest = subprocess.run(
            [
                sys.executable,
                REPO_ROOT / "bin" / "gra-ingest",
                "--run",
                run_dir,
                "--tool",
                "sbom",
                "--file",
                sbom_path,
                "--format",
                "cyclonedx",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, ingest.returncode, f"stdout:\n{ingest.stdout}\nstderr:\n{ingest.stderr}")
        self.assertIn("dependencies.json", ingest.stdout)
        self.assertIn("Added 1 dependency-posture target(s)", ingest.stdout)
        self.assertTrue((run_dir / "reports" / "dependencies.json").exists())
        self.assertTrue((run_dir / "reports" / "DEPENDENCY_RISK.md").exists())

        dependencies = json.loads((run_dir / "reports" / "dependencies.json").read_text(encoding="utf-8"))
        self.assertEqual(3, dependencies["component_count"])
        self.assertEqual(1, dependencies["vulnerability_count"])
        markdown = (run_dir / "reports" / "DEPENDENCY_RISK.md").read_text(encoding="utf-8")
        self.assertIn("Dependency risk posture", markdown)
        self.assertIn("GHSA-demo-0001", markdown)
        self.assertIn("2.0.1", markdown)

        validation = subprocess.run(
            [sys.executable, REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, validation.returncode, f"stdout:\n{validation.stdout}\nstderr:\n{validation.stderr}")
        self.assertIn("Dependencies: validated", validation.stdout)

        dashboard_path = run_dir / "reports" / "dashboard.html"
        dashboard = subprocess.run(
            [sys.executable, REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir, "--out", dashboard_path],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, dashboard.returncode, f"stdout:\n{dashboard.stdout}\nstderr:\n{dashboard.stderr}")
        dashboard_html = dashboard_path.read_text(encoding="utf-8")
        self.assertIn("Dependency risk", dashboard_html)
        self.assertIn("GHSA-demo-0001", dashboard_html)
        self.assertIn("pkg:pypi/lib-b@2.0.0", dashboard_html)

    def test_dependency_targets_cover_transitive_vulnerabilities_and_idempotency(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "cyclonedx.json"
        shutil.copy2(FIXTURES / "sbom" / "cyclonedx.json", raw_path)
        write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )

        added = append_dependency_posture_targets(run_dir)
        self.assertEqual(["TGT-DEPENDENCY-001"], [target["id"] for target in added])
        target = added[0]
        self.assertEqual("Dependency Risk", target["category"])
        self.assertEqual("high", target["risk"])
        self.assertEqual(70, target["priority"])
        self.assertIn("GHSA-demo-0001", target["scope"])
        self.assertIn("pkg:pypi/lib-b@2.0.0", target["scope"])
        self.assertIn("reports/dependencies.json", target["notes"])
        self.assertIn("evidence", " ".join(target["security_invariants"]).lower())
        self.assertEqual([], append_dependency_posture_targets(run_dir))

        validation = subprocess.run(
            [sys.executable, REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, validation.returncode, f"stdout:\n{validation.stdout}\nstderr:\n{validation.stderr}")

    def test_dependency_targets_cover_direct_vulnerabilities(self) -> None:
        run_dir = self.copy_run()
        data = analyze_dependencies(
            run_dir=run_dir,
            raw_path=FIXTURES / "sbom" / "cyclonedx.json",
            raw_result_ref="reports/scanner-results/cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )
        components = {component["id"]: component for component in data["components"]}
        direct_component = "pkg:pypi/lib-a@1.0.0"
        data["vulnerabilities"] = [
            {
                "id": "CVE-direct-0001",
                "component": direct_component,
                "severity": "Critical",
                "fixed_version": "1.0.1",
                "source": "fixture",
                "evidence_ref": "CVE-direct-0001",
                "dependency_paths": components[direct_component]["dependency_paths"],
            }
        ]
        data["vulnerability_count"] = 1
        dependencies_path = run_dir / "reports" / "dependencies.json"
        dependencies_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        added = append_dependency_posture_targets(run_dir)
        self.assertEqual(1, len(added))
        self.assertEqual("critical", added[0]["risk"])
        self.assertEqual(95, added[0]["priority"])
        self.assertEqual(["requirements.txt"], added[0]["entry_points"])

    def test_dependency_targets_skip_missing_paths_and_unknown_reachability(self) -> None:
        run_dir = self.copy_run()
        data = analyze_dependencies(
            run_dir=run_dir,
            raw_path=FIXTURES / "sbom" / "cyclonedx.json",
            raw_result_ref="reports/scanner-results/cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )
        data["vulnerabilities"][0]["dependency_paths"] = []
        dependencies_path = run_dir / "reports" / "dependencies.json"
        dependencies_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        self.assertEqual([], append_dependency_posture_targets(run_dir))

    def test_dependency_validator_rejects_count_drift_and_unknown_components(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "cyclonedx.json"
        shutil.copy2(FIXTURES / "sbom" / "cyclonedx.json", raw_path)
        write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )
        dependencies_path = run_dir / "reports" / "dependencies.json"
        dependencies = json.loads(dependencies_path.read_text(encoding="utf-8"))
        dependencies["component_count"] = 999
        dependencies["vulnerabilities"][0]["component"] = "pkg:pypi/missing@1.0.0"
        dependencies_path.write_text(json.dumps(dependencies, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        validation = subprocess.run(
            [sys.executable, REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertNotEqual(0, validation.returncode)
        self.assertIn("dependencies.component_count: value does not match components length", validation.stderr)
        self.assertIn("is not present in dependencies.components", validation.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
