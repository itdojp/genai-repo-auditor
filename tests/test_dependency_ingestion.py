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
import dependency_posture  # noqa: E402
from dependency_posture import (  # noqa: E402
    MAX_DEPENDENCY_COMPONENTS,
    MAX_DEPENDENCY_VULNERABILITIES,
    MAX_PATH_DEPTH,
    MAX_NOTE_CHARS,
    analyze_dependencies,
    append_dependency_posture_targets,
    should_ingest_dependencies,
    write_dependency_artifacts,
)


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

    def test_cyclic_cyclonedx_dependency_graph_is_bounded_and_valid(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "cyclic-cyclonedx.json"
        raw_path.write_text(
            json.dumps(
                {
                    "bomFormat": "CycloneDX",
                    "specVersion": "1.5",
                    "metadata": {"component": {"bom-ref": "root", "name": "demo", "version": "0.1.0"}},
                    "components": [
                        {"bom-ref": "lib-a", "name": "lib-a", "version": "1.0.0", "purl": "pkg:pypi/lib-a@1.0.0"},
                        {"bom-ref": "lib-b", "name": "lib-b", "version": "2.0.0", "purl": "pkg:pypi/lib-b@2.0.0"},
                    ],
                    "dependencies": [
                        {"ref": "root", "dependsOn": ["lib-a"]},
                        {"ref": "lib-a", "dependsOn": ["lib-b"]},
                        {"ref": "lib-b", "dependsOn": ["lib-a"]},
                    ],
                    "vulnerabilities": [
                        {
                            "id": "GHSA-cycle-0001",
                            "ratings": [{"severity": "high"}],
                            "affects": [{"ref": "lib-b"}],
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        data = write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/cyclic-cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )

        components = {component["id"]: component for component in data["components"]}
        self.assertEqual("transitive", components["pkg:pypi/lib-b@2.0.0"]["scope"])
        path = data["vulnerabilities"][0]["dependency_paths"][0]
        self.assertLessEqual(len(path), MAX_PATH_DEPTH)
        self.assertEqual(len(path), len(set(path)), path)
        self.assertEqual(
            ["pkg:generic/demo@0.1.0", "pkg:pypi/lib-a@1.0.0", "pkg:pypi/lib-b@2.0.0"],
            path,
        )
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

    def test_large_cyclonedx_inventory_is_capped_and_deterministic(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "large-cyclonedx.json"
        component_total = MAX_DEPENDENCY_COMPONENTS + 25
        refs = [f"lib-{index:04d}" for index in range(component_total)]
        raw_path.write_text(
            json.dumps(
                {
                    "bomFormat": "CycloneDX",
                    "specVersion": "1.5",
                    "metadata": {"component": {"bom-ref": "root", "name": "demo", "version": "0.1.0"}},
                    "components": [
                        {
                            "bom-ref": ref,
                            "name": ref,
                            "version": "1.0.0",
                            "purl": f"pkg:pypi/{ref}@1.0.0",
                        }
                        for ref in refs
                    ],
                    "dependencies": [{"ref": "root", "dependsOn": refs}],
                    "vulnerabilities": [
                        {
                            "id": f"CVE-2026-LARGE-{index:04d}",
                            "ratings": [{"severity": "low"}],
                            "affects": [{"ref": refs[index]}],
                        }
                        for index in range(MAX_DEPENDENCY_VULNERABILITIES + 5)
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        first = analyze_dependencies(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/large-cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )
        second = analyze_dependencies(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/large-cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )

        self.assertEqual(MAX_DEPENDENCY_COMPONENTS, first["component_count"])
        self.assertEqual(MAX_DEPENDENCY_VULNERABILITIES, first["vulnerability_count"])
        self.assertTrue(first["limits"]["component_limit_reached"])
        self.assertTrue(first["limits"]["vulnerability_limit_reached"])
        self.assertIn("dependency ingestion limits", first["summary"])
        self.assertEqual(
            [component["id"] for component in first["components"]],
            [component["id"] for component in second["components"]],
        )
        self.assertEqual(
            [vulnerability["id"] for vulnerability in first["vulnerabilities"]],
            [vulnerability["id"] for vulnerability in second["vulnerabilities"]],
        )

    def test_cyclonedx_component_cap_counts_normalizable_components(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "invalid-leading-components.json"
        raw_path.write_text(
            json.dumps(
                {
                    "bomFormat": "CycloneDX",
                    "metadata": {"component": {"bom-ref": "root", "name": "demo", "version": "0.1.0"}},
                    "components": [
                        *([{"bom-ref": "", "name": ""}, "not-an-object"] * (MAX_DEPENDENCY_COMPONENTS // 2 + 1)),
                        {
                            "bom-ref": "valid-lib",
                            "name": "valid-lib",
                            "version": "1.0.0",
                            "purl": "pkg:pypi/valid-lib@1.0.0",
                        },
                    ],
                    "dependencies": [{"ref": "root", "dependsOn": ["valid-lib"]}],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        data = analyze_dependencies(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/invalid-leading-components.json",
            tool="sbom",
            requested_format="cyclonedx",
        )

        components = {component["id"]: component for component in data["components"]}
        self.assertIn("pkg:pypi/valid-lib@1.0.0", components)
        self.assertEqual("direct", components["pkg:pypi/valid-lib@1.0.0"]["scope"])
        self.assertFalse(data["limits"]["component_limit_reached"])
        self.assertEqual("inventory_observed", data["status"])

    def test_cyclonedx_vulnerability_cap_counts_valid_records(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "invalid-leading-vulnerabilities.json"
        raw_path.write_text(
            json.dumps(
                {
                    "bomFormat": "CycloneDX",
                    "metadata": {"component": {"bom-ref": "root", "name": "demo", "version": "0.1.0"}},
                    "components": [
                        {
                            "bom-ref": "valid-lib",
                            "name": "valid-lib",
                            "version": "1.0.0",
                            "purl": "pkg:pypi/valid-lib@1.0.0",
                        }
                    ],
                    "dependencies": [{"ref": "root", "dependsOn": ["valid-lib"]}],
                    "vulnerabilities": [
                        *([{"ratings": [{"severity": "critical"}]}, "not-an-object"] * (MAX_DEPENDENCY_VULNERABILITIES // 2 + 1)),
                        {
                            "id": "CVE-2026-VALID-0001",
                            "ratings": [{"severity": "critical"}],
                            "affects": [{"ref": "valid-lib"}],
                        },
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        data = analyze_dependencies(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/invalid-leading-vulnerabilities.json",
            tool="sbom",
            requested_format="cyclonedx",
        )

        self.assertEqual("vulnerabilities_observed", data["status"])
        self.assertEqual(1, data["vulnerability_count"])
        self.assertEqual("CVE-2026-VALID-0001", data["vulnerabilities"][0]["id"])
        self.assertFalse(data["limits"]["vulnerability_limit_reached"])
        self.assertNotIn("dependency ingestion limits", data["summary"])

    def test_exact_dependency_limits_do_not_emit_truncation_warning(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "exact-limit-cyclonedx.json"
        raw_path.write_text(
            json.dumps(
                {
                    "bomFormat": "CycloneDX",
                    "specVersion": "1.5",
                    "metadata": {"component": {"bom-ref": "root", "name": "demo", "version": "0.1.0"}},
                    "components": [
                        {
                            "bom-ref": "valid-lib",
                            "name": "valid-lib",
                            "version": "1.0.0",
                            "purl": "pkg:pypi/valid-lib@1.0.0",
                        }
                    ],
                    "dependencies": [{"ref": "root", "dependsOn": ["valid-lib"]}],
                    "vulnerabilities": [
                        {
                            "id": f"CVE-2026-EXACT-{index:04d}",
                            "ratings": [{"severity": "low"}],
                            "affects": [{"ref": "valid-lib"}],
                        }
                        for index in range(MAX_DEPENDENCY_VULNERABILITIES)
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        data = analyze_dependencies(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/exact-limit-cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )

        self.assertEqual(MAX_DEPENDENCY_VULNERABILITIES, data["vulnerability_count"])
        self.assertFalse(data["limits"]["vulnerability_limit_reached"])
        self.assertNotIn("dependency ingestion limits", data["summary"])

    def test_oversized_dependency_input_records_parse_error_without_traceback(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "oversized-cyclonedx.json"
        raw_path.write_text(
            json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "demo"}]}, indent=2) + "\n",
            encoding="utf-8",
        )
        original_limit = dependency_posture.MAX_DEPENDENCY_INPUT_BYTES
        try:
            dependency_posture.MAX_DEPENDENCY_INPUT_BYTES = 16
            data = analyze_dependencies(
                run_dir=run_dir,
                raw_path=raw_path,
                raw_result_ref="reports/scanner-results/oversized-cyclonedx.json",
                tool="sbom",
                requested_format="cyclonedx",
            )
        finally:
            dependency_posture.MAX_DEPENDENCY_INPUT_BYTES = original_limit

        self.assertEqual("invalid", data["status"])
        self.assertEqual("invalid", data["source"]["detected_format"])
        self.assertIn("exceeds maximum dependency input size", data["parse_error"])
        self.assertNotIn("Traceback", data["parse_error"])
        self.assertEqual([], data["components"])
        self.assertEqual([], data["vulnerabilities"])

    def test_malformed_shapes_escape_markdown_and_redact_sensitive_text(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "malformed-cyclonedx.json"
        raw_secret = "ghp_123456789012345678901234567890123456"
        raw_path.write_text(
            json.dumps(
                {
                    "bomFormat": "CycloneDX",
                    "metadata": {"component": {"bom-ref": "root<script>", "name": "demo<script>", "version": "0.1.0"}},
                    "components": [
                        {
                            "bom-ref": "lib<one>",
                            "name": "lib<one>",
                            "version": "1.0.0",
                            "purl": "pkg:pypi/lib-one@1.0.0",
                            "licenses": {"license": {"id": "MIT"}},
                        },
                        {
                            "bom-ref": {"unexpected": "dict"},
                            "licenses": [{"license": {"id": "NOASSERTION"}}, {"expression": ["unexpected"]}],
                        },
                    ],
                    "dependencies": [
                        {"ref": "root<script>", "dependsOn": ["lib<one>", {"unexpected": "child"}]},
                        {"ref": ["unexpected"], "dependsOn": "not-a-list"},
                    ],
                    "vulnerabilities": [
                        {
                            "id": "GHSA-<script>-0001",
                            "source": {"name": f"<b>advisory</b> {raw_secret}"},
                            "ratings": [{"severity": "HIGH"}],
                            "recommendation": f"upgrade to 1.0.1 and remove {raw_secret}",
                            "affects": [{"ref": "lib<one>", "versions": [{"status": "fixed", "version": "1.0.1"}]}],
                            "advisories": [{"url": "<script>alert(1)</script>"}],
                        },
                        {
                            "id": "GHSA-missing-ref",
                            "ratings": [{"severity": ["critical"]}],
                            "affects": [{}],
                            "recommendation": {"unexpected": "<script>"},
                        },
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        data = write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/malformed-cyclonedx.json",
            tool="sbom<script>",
            requested_format="cyclonedx",
        )

        self.assertEqual("vulnerabilities_observed", data["status"])
        components = {component["id"]: component for component in data["components"]}
        self.assertEqual(["MIT"], components["pkg:pypi/lib-one@1.0.0"]["licenses"])
        vulnerabilities = {vulnerability["id"]: vulnerability for vulnerability in data["vulnerabilities"]}
        self.assertEqual("", vulnerabilities["GHSA-missing-ref"]["component"])
        self.assertNotIn(raw_secret, json.dumps(data, ensure_ascii=False))

        markdown = (run_dir / "reports" / "DEPENDENCY_RISK.md").read_text(encoding="utf-8")
        self.assertNotIn("<script>", markdown)
        self.assertNotIn("<b>advisory</b>", markdown)
        self.assertIn("GHSA-&lt;script&gt;-0001", markdown)
        self.assertIn("&lt;b&gt;advisory&lt;/b&gt;", markdown)
        self.assertNotIn(raw_secret, markdown)
        self.assertIn("ghp_...", markdown)

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

    def test_scanner_dependency_formats_trigger_dependency_ingestion(self) -> None:
        self.assertTrue(should_ingest_dependencies(safe_tool="trivy", fmt="cyclonedx"))
        self.assertTrue(should_ingest_dependencies(safe_tool="trivy", fmt="spdx"))
        self.assertTrue(should_ingest_dependencies(safe_tool="trivy", fmt="json"))
        self.assertTrue(should_ingest_dependencies(safe_tool="grype", fmt="json"))

    def test_trivy_vulnerability_json_links_existing_dependency_components(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        sbom_path = raw_dir / "cyclonedx.json"
        shutil.copy2(FIXTURES / "sbom" / "cyclonedx.json", sbom_path)
        write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=sbom_path,
            raw_result_ref="reports/scanner-results/cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )
        trivy_path = raw_dir / "trivy-vulnerabilities.json"
        shutil.copy2(FIXTURES / "sbom" / "trivy-vulnerabilities.json", trivy_path)

        data = write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=trivy_path,
            raw_result_ref="reports/scanner-results/trivy-vulnerabilities.json",
            tool="trivy",
            requested_format="json",
        )

        self.assertEqual("trivy", data["source"]["detected_format"])
        components = {component["id"]: component for component in data["components"]}
        self.assertIn("pkg:pypi/lib-b@2.0.0", components)
        self.assertEqual("transitive", components["pkg:pypi/lib-b@2.0.0"]["scope"])
        vulnerabilities = {vulnerability["id"]: vulnerability for vulnerability in data["vulnerabilities"]}
        self.assertIn("GHSA-demo-0001", vulnerabilities)
        trivy_vuln = vulnerabilities["CVE-2026-TRIVY-0001"]
        self.assertEqual("pkg:pypi/lib-b@2.0.0", trivy_vuln["component"])
        self.assertEqual("Critical", trivy_vuln["severity"])
        self.assertEqual("2.0.1", trivy_vuln["fixed_version"])
        self.assertEqual("trivy", trivy_vuln["source"])
        self.assertEqual(
            ["pkg:github/example/demo@0.1.0", "pkg:pypi/lib-a@1.0.0", "pkg:pypi/lib-b@2.0.0"],
            trivy_vuln["dependency_paths"][0],
        )
        unmatched = vulnerabilities["CVE-2026-TRIVY-UNMATCHED"]
        self.assertEqual("", unmatched["component"])
        self.assertEqual([], unmatched["dependency_paths"])

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

    def test_trivy_reingest_replaces_prior_trivy_vulnerability_evidence(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        sbom_path = raw_dir / "cyclonedx.json"
        shutil.copy2(FIXTURES / "sbom" / "cyclonedx.json", sbom_path)
        write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=sbom_path,
            raw_result_ref="reports/scanner-results/cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )
        trivy_path = raw_dir / "trivy-vulnerabilities.json"
        shutil.copy2(FIXTURES / "sbom" / "trivy-vulnerabilities.json", trivy_path)
        data = write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=trivy_path,
            raw_result_ref="reports/scanner-results/trivy-vulnerabilities.json",
            tool="trivy",
            requested_format="json",
        )
        self.assertIsNotNone(data)
        self.assertIn("CVE-2026-TRIVY-0001", {vulnerability["id"] for vulnerability in data["vulnerabilities"]})

        clean_trivy = raw_dir / "trivy-clean.json"
        clean_trivy.write_text(
            json.dumps(
                {
                    "SchemaVersion": 2,
                    "ArtifactName": "example/demo",
                    "Results": [{"Target": "requirements.txt", "Type": "python-pkg", "Vulnerabilities": []}],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        data = write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=clean_trivy,
            raw_result_ref="reports/scanner-results/trivy-clean.json",
            tool="trivy",
            requested_format="json",
        )
        self.assertIsNotNone(data)
        vulnerabilities = {vulnerability["id"]: vulnerability for vulnerability in data["vulnerabilities"]}
        self.assertIn("GHSA-demo-0001", vulnerabilities)
        self.assertNotIn("CVE-2026-TRIVY-0001", vulnerabilities)
        self.assertNotIn("CVE-2026-TRIVY-UNMATCHED", vulnerabilities)

    def test_unrecognized_trivy_json_does_not_overwrite_dependency_posture(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        sbom_path = raw_dir / "cyclonedx.json"
        shutil.copy2(FIXTURES / "sbom" / "cyclonedx.json", sbom_path)
        write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=sbom_path,
            raw_result_ref="reports/scanner-results/cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )
        dependencies_path = run_dir / "reports" / "dependencies.json"
        before = json.loads(dependencies_path.read_text(encoding="utf-8"))
        unsupported_trivy = raw_dir / "trivy-unsupported.json"
        unsupported_trivy.write_text(
            json.dumps({"SchemaVersion": 2, "ArtifactName": "example/demo", "UnsupportedResults": []}, indent=2) + "\n",
            encoding="utf-8",
        )

        data = write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=unsupported_trivy,
            raw_result_ref="reports/scanner-results/trivy-unsupported.json",
            tool="trivy",
            requested_format="json",
        )

        self.assertIsNone(data)
        after = json.loads(dependencies_path.read_text(encoding="utf-8"))
        self.assertEqual(before, after)

    def test_grype_vulnerability_json_links_existing_dependency_components(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        sbom_path = raw_dir / "cyclonedx.json"
        shutil.copy2(FIXTURES / "sbom" / "cyclonedx.json", sbom_path)
        write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=sbom_path,
            raw_result_ref="reports/scanner-results/cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )
        grype_path = raw_dir / "grype-vulnerabilities.json"
        shutil.copy2(FIXTURES / "sbom" / "grype-vulnerabilities.json", grype_path)

        data = write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=grype_path,
            raw_result_ref="reports/scanner-results/grype-vulnerabilities.json",
            tool="grype",
            requested_format="json",
        )

        self.assertEqual("grype", data["source"]["detected_format"])
        components = {component["id"]: component for component in data["components"]}
        self.assertIn("pkg:pypi/lib-a@1.0.0", components)
        self.assertEqual("direct", components["pkg:pypi/lib-a@1.0.0"]["scope"])
        vulnerabilities = {vulnerability["id"]: vulnerability for vulnerability in data["vulnerabilities"]}
        grype_vuln = vulnerabilities["GHSA-GRYPE-0001"]
        self.assertEqual("pkg:pypi/lib-a@1.0.0", grype_vuln["component"])
        self.assertEqual("High", grype_vuln["severity"])
        self.assertEqual("1.0.1", grype_vuln["fixed_version"])
        self.assertEqual("grype", grype_vuln["source"])
        self.assertEqual(
            ["pkg:github/example/demo@0.1.0", "pkg:pypi/lib-a@1.0.0"],
            grype_vuln["dependency_paths"][0],
        )
        unmatched = vulnerabilities["GHSA-GRYPE-UNMATCHED"]
        self.assertEqual("", unmatched["component"])
        self.assertEqual([], unmatched["dependency_paths"])

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

    def test_gra_ingest_trivy_json_updates_dependency_evidence_and_targets(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        sbom_path = raw_dir / "cyclonedx.json"
        shutil.copy2(FIXTURES / "sbom" / "cyclonedx.json", sbom_path)
        write_dependency_artifacts(
            run_dir=run_dir,
            raw_path=sbom_path,
            raw_result_ref="reports/scanner-results/cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )

        ingest = subprocess.run(
            [
                sys.executable,
                REPO_ROOT / "bin" / "gra-ingest",
                "--run",
                run_dir,
                "--tool",
                "trivy",
                "--file",
                FIXTURES / "sbom" / "trivy-vulnerabilities.json",
                "--format",
                "json",
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
        self.assertIn("Added 2 dependency-posture target(s)", ingest.stdout)
        dependencies = json.loads((run_dir / "reports" / "dependencies.json").read_text(encoding="utf-8"))
        vulnerabilities = {vulnerability["id"]: vulnerability for vulnerability in dependencies["vulnerabilities"]}
        self.assertEqual("pkg:pypi/lib-b@2.0.0", vulnerabilities["CVE-2026-TRIVY-0001"]["component"])
        targets = json.loads((run_dir / "reports" / "targets.json").read_text(encoding="utf-8"))["targets"]
        dependency_target_scopes = [target["scope"] for target in targets if str(target.get("id", "")).startswith("TGT-DEPENDENCY-")]
        self.assertTrue(any("CVE-2026-TRIVY-0001" in scope for scope in dependency_target_scopes))

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

    def test_dependency_targets_handle_malformed_files_and_bound_notes(self) -> None:
        malformed_run = self.copy_run()
        malformed_path = malformed_run / "reports" / "dependencies.json"
        malformed_path.write_text("[]\n", encoding="utf-8")
        self.assertEqual([], append_dependency_posture_targets(malformed_run))

        shutil.rmtree(malformed_run)
        run_dir = self.copy_run()
        data = analyze_dependencies(
            run_dir=run_dir,
            raw_path=FIXTURES / "sbom" / "cyclonedx.json",
            raw_result_ref="reports/scanner-results/cyclonedx.json",
            tool="sbom",
            requested_format="cyclonedx",
        )
        component_id = "pkg:pypi/lib-b@2.0.0"
        components = {component["id"]: component for component in data["components"]}
        components[component_id]["version"] = "9" * 200
        data["vulnerabilities"] = [
            {
                "id": "GHSA-" + "x" * 200,
                "component": component_id,
                "severity": "High",
                "fixed_version": "1." + "2" * 200,
                "source": "fixture-" + "source" * 100,
                "evidence_ref": "evidence",
                "dependency_paths": [[component_id, "pkg:generic/" + "nested" * 120]],
            }
        ]
        data["vulnerability_count"] = 1
        dependencies_path = run_dir / "reports" / "dependencies.json"
        dependencies_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        added = append_dependency_posture_targets(run_dir)
        self.assertEqual(1, len(added))
        self.assertLessEqual(len(added[0]["notes"]), MAX_NOTE_CHARS)
        self.assertTrue(added[0]["notes"].endswith("...<truncated>"))

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
