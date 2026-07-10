from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from validators.findings import validate_findings  # noqa: E402
from validators.registry import ValidationContext, ValidatorRegistry, core_validator_registry  # noqa: E402
from validators.run_manifest import validate_manifest_artifact_path, validate_run_manifest  # noqa: E402
from validators.scanner import validate_scanner_index  # noqa: E402
from validators.targets import validate_targets  # noqa: E402


def context_for(run_dir: Path, findings_data: dict | None = None) -> ValidationContext:
    findings_path = run_dir / "reports" / "findings.json"
    if findings_data is None and findings_path.exists():
        findings_data = json.loads(findings_path.read_text(encoding="utf-8"))
    return ValidationContext(
        lab_root=REPO_ROOT,
        run_dir=run_dir,
        findings_path=findings_path,
        findings_data=findings_data or {},
        errors=[],
        taxonomy_profiles_loaded=False,
    )


class ValidatorRegistryTests(unittest.TestCase):
    def test_registry_preserves_explicit_dispatch_order_and_rejects_invalid_names(self) -> None:
        registry = ValidatorRegistry()

        def first(context: ValidationContext) -> bool:
            context.errors.append("first")
            return True

        def second(context: ValidationContext) -> bool:
            context.errors.append("second")
            return False

        registry.register("first", first)
        registry.register("second", second)
        context = context_for(REPO_ROOT / "tests" / "fixtures" / "minimal-run")

        self.assertEqual(("first", "second"), registry.names)
        self.assertEqual({"second": False, "first": True}, registry.run(context, ["second", "first"]))
        self.assertEqual(["second", "first"], context.errors)
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register("first", first)
        with self.assertRaisesRegex(ValueError, "invalid"):
            registry.register("   ", first)
        with self.assertRaisesRegex(KeyError, "unknown validator"):
            registry.run(context, ["missing"])

    def test_manifest_paths_reject_windows_anchored_paths(self) -> None:
        run_dir = REPO_ROOT / "tests" / "fixtures" / "minimal-run"
        for value in ["C:temp\\file.txt", "C:\\temp\\file.txt", "\\temp\\file.txt"]:
            with self.subTest(value=value):
                errors: list[str] = []
                self.assertIsNone(validate_manifest_artifact_path(run_dir, value, "run_manifest.artifacts[0].path", errors))
                self.assertEqual(
                    ["run_manifest.artifacts[0].path: artifact path must be relative to the run directory"],
                    errors,
                )

    def test_core_registry_has_stable_names_and_extracted_implementations(self) -> None:
        registry = core_validator_registry()
        self.assertEqual(("findings", "targets", "scanner_index", "run_manifest"), registry.names)
        self.assertEqual("validators.findings", validate_findings.__module__)
        self.assertEqual("validators.targets", validate_targets.__module__)
        self.assertEqual("validators.scanner", validate_scanner_index.__module__)
        self.assertEqual("validators.run_manifest", validate_run_manifest.__module__)

    def test_findings_and_targets_dispatch_for_valid_fixture(self) -> None:
        run_dir = REPO_ROOT / "tests" / "fixtures" / "minimal-run"
        context = context_for(run_dir)
        results = core_validator_registry().run(context, ["findings", "targets"])
        self.assertEqual({"findings": True, "targets": True}, results)
        self.assertEqual([], context.errors)
        self.assertEqual(1, len(context.findings))

    def test_scanner_index_dispatch_for_valid_fixture(self) -> None:
        run_dir = REPO_ROOT / "tests" / "fixtures" / "advanced-workflow-run"
        context = context_for(run_dir, {})
        results = core_validator_registry().run(context, ["scanner_index"])
        self.assertEqual({"scanner_index": True}, results)
        self.assertEqual([], context.errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
