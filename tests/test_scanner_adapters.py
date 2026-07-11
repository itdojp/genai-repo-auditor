from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from scanner_adapters import (  # noqa: E402
    ADAPTERS,
    ScannerAdapterError,
    build_scan_plan,
    list_adapters,
    validate_adapter,
)
from validators.common import validate_schema  # noqa: E402


class ScannerAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))
        self.run_dir = self.work_dir / "run"
        (self.run_dir / "repo").mkdir(parents=True)
        (self.run_dir / "reports").mkdir()
        (self.run_dir / "context.json").write_text(
            json.dumps(
                {
                    "run_id": "scanner-plan-test",
                    "repo": "example/scanner-plan",
                    "target_repo_dir": "repo",
                    "reports_dir": "reports",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with suppress(OSError):
            self.tmp_parent.rmdir()

    def test_registry_has_two_valid_offline_argument_array_adapters(self) -> None:
        self.assertEqual(["gitleaks", "syft"], sorted(ADAPTERS))
        for adapter in ADAPTERS.values():
            validate_adapter(adapter)
            self.assertFalse(adapter.network_required)
            self.assertIn("{target}", " ".join(adapter.argument_template))
            self.assertIn("{output}", " ".join(adapter.argument_template))
            self.assertTrue(set(adapter.approved_sandbox_profiles).issubset({"container", "gvisor", "vm"}))
        listing = list_adapters(path_env=str(self.work_dir / "missing-bin"))
        for contract in listing["adapters"]:
            self.assertEqual(contract["executable"], contract["command_template"][0])
            self.assertEqual(["<target_repo_dir>"], contract["read_path_templates"])
            self.assertTrue(contract["write_path_templates"][0].startswith("<reports_dir>/"))

    def test_adapter_validation_rejects_shell_and_unknown_placeholders(self) -> None:
        with self.assertRaisesRegex(ScannerAdapterError, "bare executable"):
            validate_adapter(replace(ADAPTERS["gitleaks"], executable="gitleaks;touch"))
        with self.assertRaisesRegex(ScannerAdapterError, "shell-free"):
            validate_adapter(replace(ADAPTERS["gitleaks"], argument_template=("{target}", "|", "{output}")))
        with self.assertRaisesRegex(ScannerAdapterError, "unknown placeholder"):
            validate_adapter(replace(ADAPTERS["gitleaks"], argument_template=("{target}", "{secret}", "{output}")))
        with self.assertRaisesRegex(ScannerAdapterError, "sandbox profile"):
            validate_adapter(replace(ADAPTERS["gitleaks"], approved_sandbox_profiles=()))
        with self.assertRaisesRegex(ScannerAdapterError, "planning-safe sandbox profiles"):
            validate_adapter(replace(ADAPTERS["gitleaks"], approved_sandbox_profiles=("source-only",)))
        with self.assertRaisesRegex(ScannerAdapterError, "operating system"):
            validate_adapter(replace(ADAPTERS["gitleaks"], supported_operating_systems=()))

    def test_plan_is_run_relative_non_executing_and_machine_readable(self) -> None:
        plan = build_scan_plan(
            self.run_dir,
            adapter_id="gitleaks",
            sandbox_profile="container",
            path_env=str(self.work_dir / "empty-bin"),
        )

        self.assertEqual("1", plan["schema_version"])
        self.assertEqual("plan", plan["mode"])
        self.assertFalse(plan["scanner_executed"])
        self.assertFalse(plan["network_accessed"])
        self.assertEqual("repo", plan["read_paths"][0])
        self.assertEqual("reports/scanner-results/raw/gitleaks.json", plan["raw_output_path"])
        self.assertEqual(plan["raw_output_path"], plan["write_paths"][0])
        self.assertEqual("gitleaks", plan["command"][0])
        self.assertNotIn(str(self.run_dir), json.dumps(plan))
        self.assertFalse(plan["adapter"]["readiness"]["executable_available"])
        self.assertFalse(plan["adapter"]["readiness"]["version_check_executed"])
        self.assertFalse(plan["planning_readiness"]["sandbox_readiness_executed"])
        self.assertEqual("container", plan["planning_readiness"]["sandbox_profile_selected"])
        plan_schema = json.loads((REPO_ROOT / "templates" / "reports" / "scanner-plan.schema.json").read_text(encoding="utf-8"))
        self.assertTrue(set(plan_schema["required"]).issubset(plan))
        plan_errors: list[str] = []
        validate_schema(plan, plan_schema, "scanner_plan", plan_errors)
        self.assertEqual([], plan_errors)

        malformed_plan = json.loads(json.dumps(plan))
        malformed_plan["adapter"] = {}
        malformed_errors: list[str] = []
        validate_schema(malformed_plan, plan_schema, "scanner_plan", malformed_errors)
        self.assertTrue(any("scanner_plan.adapter.id: missing required field" in item for item in malformed_errors))

    def test_list_contract_does_not_require_binary(self) -> None:
        payload = list_adapters(path_env=str(self.work_dir / "missing-bin"))
        self.assertEqual("list", payload["mode"])
        self.assertFalse(payload["scanner_executed"])
        self.assertEqual(["gitleaks", "syft"], [item["id"] for item in payload["adapters"]])
        self.assertTrue(all(not item["readiness"]["executable_available"] for item in payload["adapters"]))
        schema = json.loads((REPO_ROOT / "templates" / "reports" / "scanner-adapter.schema.json").read_text(encoding="utf-8"))
        required = set(schema["required"])
        self.assertTrue(all(required.issubset(item) for item in payload["adapters"]))

    def test_plan_rejects_unsafe_paths_profiles_and_network(self) -> None:
        context_path = self.run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "../outside"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ScannerAdapterError, "reports directory"):
            build_scan_plan(self.run_dir, adapter_id="gitleaks", sandbox_profile="container")

        context["reports_dir"] = "reports"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ScannerAdapterError, "not approved"):
            build_scan_plan(self.run_dir, adapter_id="gitleaks", sandbox_profile="source-only")
        with self.assertRaisesRegex(ScannerAdapterError, "does not declare network"):
            build_scan_plan(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                network_policy="explicit-allow",
            )

    def test_gvisor_plan_is_rejected_outside_linux_and_wsl2(self) -> None:
        for operating_system in ("native-windows", "macos"):
            with self.subTest(operating_system=operating_system), mock.patch(
                "scanner_adapters.detect_environment", return_value=operating_system
            ), self.assertRaisesRegex(ScannerAdapterError, "Linux or WSL2"):
                build_scan_plan(self.run_dir, adapter_id="gitleaks", sandbox_profile="gvisor")

    def test_scanner_plan_rejects_unconfirmed_wsl(self) -> None:
        with mock.patch(
            "scanner_adapters.detect_environment", return_value="wsl-unknown"
        ), self.assertRaisesRegex(ScannerAdapterError, "confirmed WSL2"):
            build_scan_plan(self.run_dir, adapter_id="gitleaks", sandbox_profile="container")

    def test_plan_rejects_leading_dash_path_components(self) -> None:
        context_path = self.run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        for field, value in [
            ("target_repo_dir", "--config=outside"),
            ("target_repo_dir", "nested/-config"),
            ("reports_dir", "-reports"),
        ]:
            with self.subTest(field=field, value=value):
                candidate = dict(context)
                candidate[field] = value
                context_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ScannerAdapterError, "leading-dash path components"):
                    build_scan_plan(self.run_dir, adapter_id="gitleaks", sandbox_profile="container")

    def test_plan_rejects_symlinked_target_path(self) -> None:
        outside = self.work_dir / "outside-repo"
        outside.mkdir()
        (self.run_dir / "repo").rmdir()
        try:
            (self.run_dir / "repo").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink not available: {exc}")

        with self.assertRaisesRegex(ScannerAdapterError, "target repository path"):
            build_scan_plan(self.run_dir, adapter_id="syft", sandbox_profile="container")

    def test_plan_rejects_symlinked_target_even_when_destination_is_inside_run(self) -> None:
        real_repo = self.run_dir / "real-repo"
        real_repo.mkdir()
        (self.run_dir / "repo").rmdir()
        try:
            (self.run_dir / "repo").symlink_to(real_repo, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink not available: {exc}")

        with self.assertRaisesRegex(ScannerAdapterError, "symlink"):
            build_scan_plan(self.run_dir, adapter_id="gitleaks", sandbox_profile="container")

    def test_plan_rejects_symlinked_raw_output_path(self) -> None:
        outside = self.work_dir / "outside-raw"
        outside.mkdir()
        scanner_results = self.run_dir / "reports" / "scanner-results"
        try:
            scanner_results.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink not available: {exc}")

        with self.assertRaisesRegex(ScannerAdapterError, "raw scanner output path"):
            build_scan_plan(self.run_dir, adapter_id="gitleaks", sandbox_profile="container")

    def test_plan_rejects_symlinked_run_and_context(self) -> None:
        run_link = self.work_dir / "run-link"
        try:
            run_link.symlink_to(self.run_dir, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink not available: {exc}")
        with self.assertRaisesRegex(ScannerAdapterError, "run directory.*symlink"):
            build_scan_plan(run_link, adapter_id="gitleaks", sandbox_profile="container")

        outside_context = self.work_dir / "outside-context.json"
        outside_context.write_text('{"run_id":"outside"}\n', encoding="utf-8")
        context_path = self.run_dir / "context.json"
        context_path.unlink()
        context_path.symlink_to(outside_context)
        with self.assertRaisesRegex(ScannerAdapterError, "context.json.*non-symlink"):
            build_scan_plan(self.run_dir, adapter_id="syft", sandbox_profile="container")

    def test_plan_rejects_unsafe_or_secret_like_run_ids(self) -> None:
        context_path = self.run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        for run_id, message in [
            ("run id with spaces", "unsupported characters"),
            ("ghp_" + "A" * 24, "secret-like"),
        ]:
            with self.subTest(run_id=run_id):
                context["run_id"] = run_id
                context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ScannerAdapterError, message):
                    build_scan_plan(self.run_dir, adapter_id="gitleaks", sandbox_profile="container")

    def test_plan_rejects_oversized_and_non_utf8_context(self) -> None:
        context_path = self.run_dir / "context.json"
        context_path.write_bytes(b" " * 1_000_001)
        with self.assertRaisesRegex(ScannerAdapterError, "size limit"):
            build_scan_plan(self.run_dir, adapter_id="gitleaks", sandbox_profile="container")

        context_path.write_bytes(b"\xff\xfe\x00")
        with self.assertRaisesRegex(ScannerAdapterError, "valid UTF-8 JSON"):
            build_scan_plan(self.run_dir, adapter_id="syft", sandbox_profile="container")
