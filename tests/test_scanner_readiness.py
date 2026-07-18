from __future__ import annotations

import contextlib
import copy
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from scanner_readiness import (  # noqa: E402
    ScannerReadinessError,
    evaluate_scanner_readiness,
    load_scanner_readiness_report,
    validate_scanner_readiness_report,
    write_scanner_readiness_report,
)
from validators.common import validate_schema  # noqa: E402
from validators.advanced import validate_scanner_readiness_reports  # noqa: E402


class ScannerReadinessTests(unittest.TestCase):
    maxDiff = None

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
                    "run_id": "scanner-readiness-test",
                    "repo": "example/scanner-readiness",
                    "target_repo_dir": "repo",
                    "reports_dir": "reports",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    @contextlib.contextmanager
    def ready_runtime(self, *, environment: str = "linux"):
        with mock.patch("scanner_readiness.detect_environment", return_value=environment), mock.patch(
            "scanner_readiness.runtime_candidates",
            return_value=[(["/approved/docker", "--host", "unix:///approved/docker.sock"], "docker")],
        ), mock.patch("scanner_readiness._probe_command", return_value=0) as probe, mock.patch(
            "scanner_readiness.shutil.which", return_value=None
        ):
            yield probe

    def test_gitleaks_and_syft_ready_reports_are_closed_bounded_and_non_executing(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "templates" / "reports" / "scanner-readiness.schema.json").read_text(encoding="utf-8")
        )
        for adapter_id in ("gitleaks", "syft"):
            with self.subTest(adapter_id=adapter_id), self.ready_runtime() as probe:
                report = evaluate_scanner_readiness(
                    self.run_dir,
                    adapter_id=adapter_id,
                    sandbox_profile="container",
                    env={"PATH": "/approved"},
                )
            self.assertEqual("ready", report["state"])
            self.assertEqual(["ready"], report["reason_codes"])
            self.assertFalse(report["scanner_executed"])
            self.assertFalse(report["network_accessed"])
            self.assertFalse(report["probes"]["scanner_executed"])
            self.assertFalse(report["probes"]["image_pulled"])
            self.assertFalse(report["probes"]["remote_runtime_contacted"])
            self.assertTrue(report["probes"]["version_check_executed"])
            self.assertEqual(2, probe.call_count)
            commands = [call.args[0] for call in probe.call_args_list]
            self.assertEqual("version", commands[0][-1])
            self.assertEqual(["image", "inspect"], commands[1][-3:-1])
            self.assertFalse(any("run" in command for command in commands))
            self.assertNotIn(str(self.run_dir), json.dumps(report))
            errors: list[str] = []
            validate_schema(report, schema, "scanner_readiness", errors)
            self.assertEqual([], errors)

    def test_runtime_blocking_categories_are_precise(self) -> None:
        common = {
            "run_dir": self.run_dir,
            "adapter_id": "gitleaks",
            "sandbox_profile": "container",
            "env": {"PATH": "/approved"},
        }
        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness.runtime_candidates", return_value=[]
        ), mock.patch("scanner_readiness._probe_command") as missing_probe, mock.patch(
            "scanner_readiness.shutil.which", return_value=None
        ):
            missing = evaluate_scanner_readiness(**common)
        self.assertIn("runtime_missing", missing["reason_codes"])
        self.assertFalse(missing["runtime"]["probe_executed"])
        self.assertFalse(missing["probes"]["runtime_probe_executed"])
        self.assertFalse(missing["probes"]["version_check_executed"])
        missing_probe.assert_not_called()

        impossible_probe = copy.deepcopy(missing)
        impossible_probe["runtime"]["probe_executed"] = True
        impossible_probe["probes"]["runtime_probe_executed"] = True
        impossible_probe["probes"]["version_check_executed"] = True
        with self.assertRaisesRegex(ScannerReadinessError, "runtime probe requires a runtime candidate"):
            validate_scanner_readiness_report(impossible_probe)

        schema = json.loads(
            (REPO_ROOT / "templates" / "reports" / "scanner-readiness.schema.json").read_text(encoding="utf-8")
        )
        missing_candidate_condition = next(
            condition
            for condition in schema["allOf"]
            if condition.get("if", {})
            .get("properties", {})
            .get("runtime", {})
            .get("properties", {})
            .get("candidate_available", {})
            .get("const")
            is False
        )
        self.assertFalse(
            missing_candidate_condition["then"]["properties"]["runtime"]["properties"]["probe_executed"]["const"]
        )

        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness.runtime_candidates", return_value=[(["docker"], "docker")]
        ), mock.patch("scanner_readiness._probe_command", return_value=1), mock.patch(
            "scanner_readiness.shutil.which", return_value=None
        ):
            unavailable = evaluate_scanner_readiness(**common)
        self.assertIn("runtime_unavailable", unavailable["reason_codes"])

        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness.runtime_candidates", return_value=[(["docker"], "docker")]
        ), mock.patch("scanner_readiness._probe_command", side_effect=[0, 1]), mock.patch(
            "scanner_readiness.shutil.which", return_value=None
        ):
            image_missing = evaluate_scanner_readiness(**common)
        self.assertIn("image_not_local", image_missing["reason_codes"])

    def test_both_adapters_cover_every_major_non_path_blocking_category(self) -> None:
        for adapter_id in ("gitleaks", "syft"):
            common = {
                "run_dir": self.run_dir,
                "adapter_id": adapter_id,
                "sandbox_profile": "container",
                "env": {"PATH": "/approved"},
            }
            cases: list[tuple[str, dict[str, Any], list[object]]] = [
                ("runtime_missing", {}, [mock.patch("scanner_readiness.runtime_candidates", return_value=[])]),
                (
                    "runtime_remote",
                    {"env": {"PATH": "/approved", "DOCKER_HOST": "tcp://remote.invalid:2376"}},
                    [mock.patch("scanner_readiness.runtime_candidates", return_value=[(["docker"], "docker")])],
                ),
                (
                    "runtime_unavailable",
                    {},
                    [
                        mock.patch("scanner_readiness.runtime_candidates", return_value=[(["docker"], "docker")]),
                        mock.patch("scanner_readiness._probe_command", return_value=1),
                    ],
                ),
                (
                    "image_not_local",
                    {},
                    [
                        mock.patch("scanner_readiness.runtime_candidates", return_value=[(["docker"], "docker")]),
                        mock.patch("scanner_readiness._probe_command", side_effect=[0, 1]),
                    ],
                ),
                (
                    "platform_unsupported",
                    {},
                    [
                        mock.patch("scanner_readiness.detect_environment", return_value="unsupported"),
                        mock.patch("scanner_readiness.runtime_candidates", return_value=[]),
                    ],
                ),
                (
                    "sandbox_unsupported",
                    {"sandbox_profile": "source-only"},
                    [mock.patch("scanner_readiness.runtime_candidates", return_value=[(["docker"], "docker")])],
                ),
                (
                    "resource_limits_unavailable",
                    {"sandbox_profile": "source-only"},
                    [mock.patch("scanner_readiness.runtime_candidates", return_value=[(["docker"], "docker")])],
                ),
                (
                    "credential_environment_present",
                    {"env": {"PATH": "/approved", "NPM_TOKEN": "not-reported"}},
                    [mock.patch("scanner_readiness.runtime_candidates", return_value=[(["docker"], "docker")])],
                ),
                (
                    "network_policy_unsupported",
                    {"network_policy": "explicit-allow"},
                    [mock.patch("scanner_readiness.runtime_candidates", return_value=[(["docker"], "docker")])],
                ),
            ]
            for reason, overrides, patches in cases:
                arguments = {**common, **overrides}
                with self.subTest(adapter_id=adapter_id, reason=reason), contextlib.ExitStack() as stack:
                    stack.enter_context(mock.patch("scanner_readiness.detect_environment", return_value="linux"))
                    stack.enter_context(mock.patch("scanner_readiness.shutil.which", return_value=None))
                    for patcher in patches:
                        stack.enter_context(patcher)
                    report = evaluate_scanner_readiness(**arguments)
                self.assertIn(reason, report["reason_codes"])

            for image_reason, configured_image in (
                ("image_not_configured", None),
                ("image_not_digest_pinned", f"registry.invalid/{adapter_id}:latest"),
            ):
                with self.subTest(adapter_id=adapter_id, reason=image_reason), mock.patch(
                    "scanner_readiness.detect_environment", return_value="linux"
                ), mock.patch(
                    "scanner_readiness.runtime_candidates", return_value=[(["docker"], "docker")]
                ), mock.patch(
                    "scanner_readiness.shutil.which", return_value=None
                ), mock.patch.dict(
                    "scanner_readiness.CONTAINER_IMAGES", {adapter_id: configured_image}
                ):
                    report = evaluate_scanner_readiness(**common)
                self.assertIn(image_reason, report["reason_codes"])

            with self.subTest(adapter_id=adapter_id, reason="gvisor_missing"), self.ready_runtime():
                report = evaluate_scanner_readiness(
                    self.run_dir,
                    adapter_id=adapter_id,
                    sandbox_profile="gvisor",
                    env={"PATH": "/approved"},
                )
            self.assertIn("gvisor_missing", report["reason_codes"])

    def test_both_adapters_cover_every_major_path_blocking_category(self) -> None:
        def new_run(name: str, *, target: str = "repo", reports: str = "reports") -> Path:
            run_dir = self.work_dir / name
            run_dir.mkdir()
            (run_dir / "context.json").write_text(
                json.dumps({"run_id": name, "target_repo_dir": target, "reports_dir": reports}) + "\n",
                encoding="utf-8",
            )
            return run_dir

        for adapter_id in ("gitleaks", "syft"):
            fixtures: list[tuple[str, Path]] = []

            missing_target = new_run(f"{adapter_id}-target")
            (missing_target / "reports").mkdir()
            fixtures.append(("target_unsafe", missing_target))

            missing_reports = new_run(f"{adapter_id}-reports")
            (missing_reports / "repo").mkdir()
            fixtures.append(("reports_path_unsafe", missing_reports))

            overlap = new_run(f"{adapter_id}-overlap", reports="repo/reports")
            (overlap / "repo" / "reports").mkdir(parents=True)
            fixtures.append(("path_overlap", overlap))

            unsafe_output = new_run(f"{adapter_id}-output")
            (unsafe_output / "repo").mkdir()
            raw = unsafe_output / "reports" / "scanner-results" / "raw"
            raw.mkdir(parents=True)
            (raw / f"{adapter_id}.json").write_text("[]\n", encoding="utf-8")
            fixtures.append(("output_path_unsafe", unsafe_output))

            unsafe_staging = new_run(f"{adapter_id}-staging")
            (unsafe_staging / "repo").mkdir()
            staging = unsafe_staging / "reports" / "scanner-results" / ".gra-scan-staging"
            staging.parent.mkdir(parents=True)
            staging.write_text("not-a-directory\n", encoding="utf-8")
            fixtures.append(("staging_path_unsafe", unsafe_staging))

            for reason, run_dir in fixtures:
                with self.subTest(adapter_id=adapter_id, reason=reason), mock.patch(
                    "scanner_readiness.detect_environment", return_value="linux"
                ), mock.patch(
                    "scanner_readiness.runtime_candidates", return_value=[]
                ), mock.patch(
                    "scanner_readiness.shutil.which", return_value=None
                ):
                    report = evaluate_scanner_readiness(
                        run_dir,
                        adapter_id=adapter_id,
                        sandbox_profile="container",
                        env={"PATH": "/missing"},
                    )
                self.assertIn(reason, report["reason_codes"])

    def test_image_configuration_and_digest_categories_are_precise(self) -> None:
        with self.ready_runtime(), mock.patch.dict(
            "scanner_readiness.CONTAINER_IMAGES", {"gitleaks": None}
        ):
            missing = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                env={"PATH": "/approved"},
            )
        self.assertIn("image_not_configured", missing["reason_codes"])
        self.assertNotIn("image_not_digest_pinned", missing["reason_codes"])

        with self.ready_runtime(), mock.patch.dict(
            "scanner_readiness.CONTAINER_IMAGES", {"gitleaks": "registry.example/gitleaks:8.30.1"}
        ):
            mutable = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                env={"PATH": "/approved"},
            )
        self.assertIn("image_not_digest_pinned", mutable["reason_codes"])
        self.assertNotIn("image_not_configured", mutable["reason_codes"])

    def test_remote_runtime_and_credentials_are_rejected_without_values_or_probes(self) -> None:
        secret = "never-print-this-secret"
        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness._probe_command"
        ) as probe, mock.patch("scanner_readiness.shutil.which", return_value="/approved/docker"):
            report = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="syft",
                sandbox_profile="container",
                env={
                    "PATH": "/approved",
                    "DOCKER_HOST": "tcp://remote.example:2376",
                    "GITHUB_TOKEN": secret,
                },
            )
        probe.assert_not_called()
        self.assertEqual("blocked", report["state"])
        self.assertIn("runtime_remote", report["reason_codes"])
        self.assertIn("credential_environment_present", report["reason_codes"])
        serialized = json.dumps(report)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("tcp://", serialized)
        self.assertEqual(["DOCKER_HOST"], report["runtime"]["remote_environment_names"])
        self.assertEqual(["GITHUB_TOKEN"], report["credentials"]["environment_names"])

    def test_credential_classifier_is_case_insensitive_and_covers_common_ecosystems(self) -> None:
        credential_names = {
            "aws_session_token": "secret-a",
            "DOCKER_AUTH_CONFIG": "secret-b",
            "NPM_TOKEN": "secret-c",
            "PYPI_API_TOKEN": "secret-d",
            "SERVICE_PASSWORD": "secret-e",
        }
        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness._probe_command"
        ) as probe, mock.patch("scanner_readiness.shutil.which", return_value="/approved/docker"):
            report = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                env={"PATH": "/approved", **credential_names},
            )
        probe.assert_not_called()
        self.assertEqual(
            ["AWS_SESSION_TOKEN", "DOCKER_AUTH_CONFIG", "NPM_TOKEN", "PYPI_API_TOKEN", "SERVICE_PASSWORD"],
            report["credentials"]["environment_names"],
        )
        serialized = json.dumps(report)
        for value in credential_names.values():
            self.assertNotIn(value, serialized)

    def test_platform_and_gvisor_boundaries_fail_closed(self) -> None:
        with mock.patch("scanner_readiness.detect_environment", return_value="unsupported"), mock.patch(
            "scanner_readiness.runtime_candidates", return_value=[]
        ), mock.patch("scanner_readiness.shutil.which", return_value=None):
            unsupported = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                env={"PATH": "/missing"},
            )
        self.assertEqual("unsupported", unsupported["state"])
        self.assertIn("platform_unsupported", unsupported["reason_codes"])

        with self.ready_runtime(environment="macos"):
            experimental = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                env={"PATH": "/approved"},
            )
        self.assertEqual("experimental", experimental["state"])
        self.assertEqual(["ready"], experimental["reason_codes"])

        with self.ready_runtime(environment="native-windows"):
            windows = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="syft",
                sandbox_profile="container",
                env={"PATH": "/approved"},
            )
        self.assertEqual("experimental", windows["state"])

        with self.ready_runtime(environment="wsl2"):
            wsl2 = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="syft",
                sandbox_profile="container",
                env={"PATH": "/approved"},
            )
        self.assertEqual("ready", wsl2["state"])

        with self.ready_runtime():
            gvisor = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="gvisor",
                env={"PATH": "/approved"},
            )
        self.assertEqual("blocked", gvisor["state"])
        self.assertIn("gvisor_missing", gvisor["reason_codes"])

    def test_unsupported_profile_and_network_policy_return_bounded_blocked_reports(self) -> None:
        with self.ready_runtime():
            profile = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="source-only",
                env={"PATH": "/approved"},
            )
        self.assertEqual("blocked", profile["state"])
        self.assertIn("sandbox_unsupported", profile["reason_codes"])
        self.assertIn("resource_limits_unavailable", profile["reason_codes"])
        self.assertTrue(profile["paths"]["target_safe"])
        self.assertTrue(profile["paths"]["reports_safe"])
        self.assertFalse(profile["runtime"]["probe_executed"])

        with self.ready_runtime():
            network = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="syft",
                sandbox_profile="container",
                network_policy="explicit-allow",
                env={"PATH": "/approved"},
            )
        self.assertEqual("blocked", network["state"])
        self.assertEqual(["network_policy_unsupported"], network["reason_codes"])
        self.assertFalse(network["sandbox"]["network_disabled"])
        self.assertFalse(network["runtime"]["probe_executed"])

    def test_unsafe_missing_and_symlink_paths_fail_closed(self) -> None:
        (self.run_dir / "repo").rmdir()
        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness.runtime_candidates", return_value=[]
        ), mock.patch("scanner_readiness.shutil.which", return_value=None):
            missing = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                env={"PATH": "/missing"},
            )
        self.assertIn("target_unsafe", missing["reason_codes"])

        outside = self.work_dir / "outside"
        outside.mkdir()
        try:
            (self.run_dir / "repo").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink not available: {exc}")
        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness.runtime_candidates", return_value=[]
        ), mock.patch("scanner_readiness.shutil.which", return_value=None):
            symlink = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="syft",
                sandbox_profile="container",
                env={"PATH": "/missing"},
            )
        self.assertIn("target_unsafe", symlink["reason_codes"])
        self.assertNotIn(str(outside), json.dumps(symlink))

    def test_reports_symlink_and_target_overlap_fail_closed(self) -> None:
        outside = self.work_dir / "outside-reports"
        outside.mkdir()
        (self.run_dir / "reports").rmdir()
        try:
            (self.run_dir / "reports").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink not available: {exc}")
        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness.runtime_candidates", return_value=[]
        ), mock.patch("scanner_readiness.shutil.which", return_value=None):
            symlink = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                env={"PATH": "/missing"},
            )
        self.assertIn("reports_path_unsafe", symlink["reason_codes"])
        self.assertNotIn(str(outside), json.dumps(symlink))

        (self.run_dir / "reports").unlink()
        nested_reports = self.run_dir / "repo" / "reports"
        nested_reports.mkdir()
        context_path = self.run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "repo/reports"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")
        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness.runtime_candidates", return_value=[]
        ), mock.patch("scanner_readiness.shutil.which", return_value=None):
            overlap = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="syft",
                sandbox_profile="container",
                env={"PATH": "/missing"},
            )
        self.assertIn("path_overlap", overlap["reason_codes"])
        self.assertTrue(overlap["paths"]["target_safe"])
        self.assertTrue(overlap["paths"]["reports_safe"])

    def test_existing_output_and_unsafe_staging_paths_fail_closed(self) -> None:
        raw_dir = self.run_dir / "reports" / "scanner-results" / "raw"
        raw_dir.mkdir(parents=True)
        raw_output = raw_dir / "gitleaks.json"
        raw_output.write_text("[]\n", encoding="utf-8")
        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness.runtime_candidates", return_value=[]
        ), mock.patch("scanner_readiness.shutil.which", return_value=None):
            output = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                env={"PATH": "/missing"},
            )
        self.assertIn("output_path_unsafe", output["reason_codes"])
        self.assertFalse(output["paths"]["output_safe"])

        raw_output.unlink()
        staging = self.run_dir / "reports" / "scanner-results" / ".gra-scan-staging"
        staging.write_text("not-a-directory\n", encoding="utf-8")
        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness.runtime_candidates", return_value=[]
        ), mock.patch("scanner_readiness.shutil.which", return_value=None):
            staged = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                env={"PATH": "/missing"},
            )
        self.assertIn("staging_path_unsafe", staged["reason_codes"])
        self.assertFalse(staged["paths"]["staging_safe"])

    def test_non_directory_intermediate_output_component_fails_closed(self) -> None:
        scanner_results = self.run_dir / "reports" / "scanner-results"
        scanner_results.write_text("not-a-directory\n", encoding="utf-8")
        with mock.patch("scanner_readiness.detect_environment", return_value="linux"), mock.patch(
            "scanner_readiness.runtime_candidates", return_value=[]
        ), mock.patch("scanner_readiness.shutil.which", return_value=None):
            report = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="syft",
                sandbox_profile="container",
                env={"PATH": "/missing"},
            )
        self.assertTrue(report["paths"]["reports_safe"])
        self.assertFalse(report["paths"]["output_safe"])
        self.assertFalse(report["paths"]["staging_safe"])
        self.assertIn("output_path_unsafe", report["reason_codes"])
        self.assertIn("staging_path_unsafe", report["reason_codes"])

    def test_report_validation_rejects_unknown_fields_unbounded_text_and_inconsistency(self) -> None:
        with self.ready_runtime():
            report = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                env={"PATH": "/approved"},
            )
        mutations = []
        unknown_top = copy.deepcopy(report)
        unknown_top["unknown"] = True
        mutations.append(unknown_top)
        unknown_nested = copy.deepcopy(report)
        unknown_nested["runtime"]["daemon_url"] = "unix:///private"
        mutations.append(unknown_nested)
        long_step = copy.deepcopy(report)
        long_step["next_steps"] = ["x" * 257]
        mutations.append(long_step)
        exposed = copy.deepcopy(report)
        exposed["credentials"]["values_exposed"] = True
        mutations.append(exposed)
        inconsistent = copy.deepcopy(report)
        inconsistent["image"]["local_available"] = True
        inconsistent["image"]["digest_pinned"] = False
        mutations.append(inconsistent)
        unknown_adapter = copy.deepcopy(report)
        unknown_adapter["adapter_id"] = "unapproved"
        mutations.append(unknown_adapter)
        for candidate in mutations:
            with self.subTest(candidate=list(candidate)), self.assertRaises(ScannerReadinessError):
                validate_scanner_readiness_report(candidate)

    def test_report_write_load_and_symlink_rejection(self) -> None:
        with self.ready_runtime():
            report = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="syft",
                sandbox_profile="container",
                env={"PATH": "/approved"},
            )
        path = write_scanner_readiness_report(self.run_dir, report)
        self.assertEqual("reports/scanner-readiness/syft.json", path.relative_to(self.run_dir).as_posix())
        self.assertEqual(report, load_scanner_readiness_report(self.run_dir, "syft"))
        self.assertIsNone(
            load_scanner_readiness_report(
                self.run_dir,
                "syft",
                sandbox_profile="gvisor",
                network_policy="disabled",
            )
        )
        path.unlink()
        outside = self.work_dir / "outside.json"
        outside.write_text(json.dumps(report), encoding="utf-8")
        try:
            path.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink not available: {exc}")
        with self.assertRaisesRegex(ScannerReadinessError, "non-symlink"):
            load_scanner_readiness_report(self.run_dir, "syft")

    def test_report_validator_accepts_valid_and_rejects_unknown_nested_fields(self) -> None:
        with self.ready_runtime():
            report = evaluate_scanner_readiness(
                self.run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                env={"PATH": "/approved"},
            )
        path = write_scanner_readiness_report(self.run_dir, report)
        errors: list[str] = []
        self.assertTrue(validate_scanner_readiness_reports(self.run_dir, errors))
        self.assertEqual([], errors)

        poisoned = copy.deepcopy(report)
        poisoned["runtime"]["daemon_url"] = "tcp://private.example"
        path.write_text(json.dumps(poisoned) + "\n", encoding="utf-8")
        errors = []
        self.assertTrue(validate_scanner_readiness_reports(self.run_dir, errors))
        self.assertTrue(any("runtime fields are invalid" in item for item in errors), errors)
        self.assertNotIn("private.example", json.dumps(errors))

    def test_cli_readiness_only_runs_bounded_runtime_probes_and_plan_reuses_report(self) -> None:
        mock_bin = self.work_dir / "bin"
        mock_bin.mkdir()
        command_log = self.work_dir / "runtime-commands.log"
        docker = mock_bin / "docker"
        docker.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            f"printf '%s\\n' \"$*\" >> {command_log}\n"
            "case \"$*\" in\n"
            "  *' version') exit 0 ;;\n"
            "  *' image inspect '*) exit 0 ;;\n"
            "  *) exit 97 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        docker.chmod(docker.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        env = {
            "PATH": str(mock_bin),
            "HOME": str(self.work_dir / "home"),
            "LANG": "C.UTF-8",
        }
        cli = REPO_ROOT / "bin" / "gra-scan"
        readiness = subprocess.run(
            [
                sys.executable,
                str(cli),
                "--run",
                str(self.run_dir),
                "--tool",
                "gitleaks",
                "--readiness",
                "--json",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        self.assertEqual(0, readiness.returncode, readiness.stderr)
        payload = json.loads(readiness.stdout)
        self.assertIn(payload["state"], {"ready", "experimental"})
        commands = command_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(2, len(commands), commands)
        self.assertTrue(any(command.endswith(" version") for command in commands))
        self.assertTrue(any(" image inspect " in command for command in commands))
        self.assertFalse(any(" run " in f" {command} " or " pull " in f" {command} " for command in commands))

        plan = subprocess.run(
            [
                sys.executable,
                str(cli),
                "--run",
                str(self.run_dir),
                "--tool",
                "gitleaks",
                "--plan",
                "--json",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        self.assertEqual(0, plan.returncode, plan.stderr)
        plan_payload = json.loads(plan.stdout)
        self.assertTrue(plan_payload["execution_readiness"]["checked"])
        self.assertEqual(payload["state"], plan_payload["execution_readiness"]["state"])
        self.assertEqual(commands, command_log.read_text(encoding="utf-8").splitlines())

    def test_cli_does_not_persist_when_target_aliases_disagree_or_overlap(self) -> None:
        context_path = self.run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["repo_dir"] = str(self.run_dir / "reports")
        context["target_repo_dir"] = "repo"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")
        cli = REPO_ROOT / "bin" / "gra-scan"
        result = subprocess.run(
            [
                sys.executable,
                str(cli),
                "--run",
                str(self.run_dir),
                "--tool",
                "gitleaks",
                "--readiness",
                "--json",
            ],
            cwd=REPO_ROOT,
            env={"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        self.assertEqual(1, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("blocked", report["state"])
        self.assertIn("target_unsafe", report["reason_codes"])
        self.assertFalse((self.run_dir / "reports" / "scanner-readiness").exists())
        with self.assertRaisesRegex(ScannerReadinessError, "persistence is unsafe"):
            write_scanner_readiness_report(self.run_dir, report)

    def test_cli_readiness_failure_redacts_local_path_and_username(self) -> None:
        secret_path = self.work_dir / "private-user-name" / "missing-run"
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "gra-scan"),
                "--run",
                str(secret_path),
                "--tool",
                "gitleaks",
                "--readiness",
                "--json",
            ],
            cwd=REPO_ROOT,
            env={"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual("gra-scan: readiness_evaluation_failed\n", result.stderr)
        self.assertNotIn("private-user-name", result.stderr)

    def test_cli_readiness_usage_errors_do_not_echo_invalid_profile_or_policy_values(self) -> None:
        cli = REPO_ROOT / "bin" / "gra-scan"
        for option in ("--sandbox-profile", "--network-policy"):
            secret_like_value = "private-user-name-token"
            result = subprocess.run(
                [
                    sys.executable,
                    str(cli),
                    "--run",
                    str(self.run_dir),
                    "--tool",
                    "gitleaks",
                    "--readiness",
                    option,
                    secret_like_value,
                ],
                cwd=REPO_ROOT,
                env={"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8"},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
            )
            with self.subTest(option=option):
                self.assertEqual(2, result.returncode)
                self.assertNotIn(secret_like_value, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
