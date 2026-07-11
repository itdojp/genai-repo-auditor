from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

import platform_support  # noqa: E402


class PlatformSupportTests(unittest.TestCase):
    def test_environment_classification_distinguishes_native_windows_and_wsl2(self) -> None:
        self.assertEqual(
            "native-windows",
            platform_support.classify_environment(system="Windows", os_name="nt", env={}),
        )
        self.assertEqual(
            "wsl-unknown",
            platform_support.classify_environment(
                system="Linux",
                os_name="posix",
                env={"WSL_INTEROP": "/run/WSL/1_interop"},
            ),
        )
        self.assertEqual(
            "wsl2",
            platform_support.classify_environment(
                system="Linux",
                os_name="posix",
                env={},
                osrelease="6.6.87.2-microsoft-standard-WSL2",
            ),
        )
        self.assertEqual(
            "linux",
            platform_support.classify_environment(system="Linux", os_name="posix", env={}),
        )
        self.assertEqual(
            "macos",
            platform_support.classify_environment(system="Darwin", os_name="posix", env={}),
        )

    def test_native_windows_report_is_explicit_and_fail_closed_for_missing_dirfd(self) -> None:
        with (
            unittest.mock.patch.object(platform_support, "detect_environment", return_value="native-windows"),
            unittest.mock.patch.object(platform_support, "dirfd_report_writes_supported", return_value=False),
        ):
            report = platform_support.platform_support_report()

        self.assertEqual("warning", report["status"])
        self.assertEqual("native-windows", report["environment"])
        self.assertEqual("supported", report["features"]["workflow_plan_execute_resume"])
        self.assertEqual("unsupported-fail-closed", report["features"]["efficacy_report_generation"])
        self.assertEqual(
            "experimental-docker-desktop-linux-containers",
            report["features"]["scanner_execution"],
        )
        self.assertTrue(any("WSL2" in item for item in report["diagnostics"]))

    def test_wsl2_uses_linux_scanner_boundary(self) -> None:
        with (
            unittest.mock.patch.object(platform_support, "detect_environment", return_value="wsl2"),
            unittest.mock.patch.object(platform_support, "dirfd_report_writes_supported", return_value=True),
        ):
            report = platform_support.platform_support_report()

        self.assertEqual("ok", report["status"])
        self.assertTrue(report["wsl_detected"])
        self.assertTrue(report["wsl2_confirmed"])
        self.assertEqual("supported", report["features"]["efficacy_report_generation"])
        self.assertEqual("supported-local-docker-or-podman", report["features"]["scanner_execution"])

    def test_unconfirmed_wsl_does_not_claim_wsl2_support(self) -> None:
        with (
            unittest.mock.patch.object(platform_support, "detect_environment", return_value="wsl-unknown"),
            unittest.mock.patch.object(platform_support, "dirfd_report_writes_supported", return_value=True),
        ):
            report = platform_support.platform_support_report()

        self.assertEqual("warning", report["status"])
        self.assertTrue(report["wsl_detected"])
        self.assertFalse(report["wsl2_confirmed"])
        self.assertEqual("unsupported", report["features"]["workflow_plan_execute_resume"])
        self.assertEqual("experimental-untested-wsl", report["features"]["efficacy_report_generation"])
        self.assertTrue(any("WSL2" in item for item in report["diagnostics"]))

    def test_macos_scanner_execution_remains_experimental(self) -> None:
        with (
            unittest.mock.patch.object(platform_support, "detect_environment", return_value="macos"),
            unittest.mock.patch.object(platform_support, "dirfd_report_writes_supported", return_value=True),
        ):
            report = platform_support.platform_support_report()

        self.assertEqual("experimental-local-docker", report["features"]["scanner_execution"])

    def test_missing_dirfd_capabilities_warn_on_other_supported_platforms(self) -> None:
        for environment in ("linux", "macos"):
            with self.subTest(environment=environment), unittest.mock.patch.object(
                platform_support, "detect_environment", return_value=environment
            ), unittest.mock.patch.object(
                platform_support, "dirfd_report_writes_supported", return_value=False
            ):
                report = platform_support.platform_support_report()

            self.assertEqual("warning", report["status"])
            self.assertEqual("unsupported-fail-closed", report["features"]["efficacy_report_generation"])

    def test_unsupported_environment_never_claims_efficacy_generation(self) -> None:
        for dirfd in (False, True):
            with self.subTest(dirfd=dirfd), unittest.mock.patch.object(
                platform_support, "detect_environment", return_value="unsupported"
            ), unittest.mock.patch.object(
                platform_support, "dirfd_report_writes_supported", return_value=dirfd
            ):
                report = platform_support.platform_support_report()

            self.assertEqual("warning", report["status"])
            self.assertEqual("unsupported", report["features"]["efficacy_report_generation"])

    def test_unconfirmed_wsl_without_dirfd_capabilities_fails_closed(self) -> None:
        with unittest.mock.patch.object(
            platform_support, "detect_environment", return_value="wsl-unknown"
        ), unittest.mock.patch.object(
            platform_support, "dirfd_report_writes_supported", return_value=False
        ):
            report = platform_support.platform_support_report()

        self.assertEqual("warning", report["status"])
        self.assertEqual("unsupported-fail-closed", report["features"]["efficacy_report_generation"])

    def test_support_matrix_documents_required_platform_boundaries(self) -> None:
        english = (REPO_ROOT / "docs" / "WINDOWS_WSL_SUPPORT.md").read_text(encoding="utf-8")
        japanese = (REPO_ROOT / "docs" / "ja" / "WINDOWS_WSL_SUPPORT.ja.md").read_text(encoding="utf-8")
        for marker in (
            "Native Windows",
            "WSL2",
            "Linux",
            "macOS",
            "gra-audit --mode prepare",
            "gra-run",
            "gra-efficacy-benchmark",
            "gra-scan --plan",
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "https://cli.github.com/manual/gh_help_environment",
            "--network=none",
        ):
            self.assertIn(marker, english)
        for marker in ("native Windows", "WSL2", "gra-run", "GH_TOKEN", "GITHUB_TOKEN", "fail closed"):
            self.assertIn(marker, japanese)


if __name__ == "__main__":
    unittest.main(verbosity=2)
