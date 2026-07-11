from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMMAND = REPO_ROOT / "bin" / "gra-efficacy-benchmark"
sys.path.insert(0, str(REPO_ROOT / "lib"))

from efficacy_benchmark import (  # noqa: E402
    EfficacyBenchmarkError,
    analyze_fixture_case,
    build_fixture_report,
    score_cases,
    select_cases,
    write_report,
)
from efficacy_corpus import (  # noqa: E402
    EfficacyCorpusError,
    load_corpus,
    load_corpus_fixture_texts,
    validate_schema_object,
)
import efficacy_benchmark  # noqa: E402


class EfficacyBenchmarkTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        parent = REPO_ROOT / ".test-tmp"
        parent.mkdir(exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)
        with contextlib.suppress(OSError):
            (REPO_ROOT / ".test-tmp").rmdir()

    def run_command(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATH"] = str(self.work / "empty-path")
        return subprocess.run(
            [sys.executable, COMMAND, *args],
            cwd=self.work,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )

    def test_core_fixture_report_is_deterministic_and_scores_expected_outcomes(self) -> None:
        first = build_fixture_report(REPO_ROOT)
        second = build_fixture_report(REPO_ROOT)

        self.assertEqual(first, second)
        self.assertEqual("deterministic-fixture", first["mode"])
        self.assertEqual("synthetic-reference-rules-v2", first["execution"]["detector_id"])
        self.assertEqual(20, first["execution"]["selected_case_count"])
        self.assertEqual(20, first["execution"]["supported_case_count"])
        self.assertEqual(
            {
                "true_positives": 10,
                "false_positives": 0,
                "false_negatives": 0,
                "true_negatives": 10,
                "prediction_count": 10,
            },
            first["scores"]["counts"],
        )
        self.assertEqual(
            {"precision": 1.0, "recall": 1.0, "f1": 1.0},
            first["scores"]["rates"],
        )
        self.assertEqual(
            {"agreed": 10, "eligible": 10, "rate": 1.0},
            first["scores"]["severity_agreement"],
        )
        self.assertEqual(
            {"covered": 20, "selected": 20, "rate": 1.0},
            first["scores"]["target_coverage"],
        )
        self.assertEqual(10, first["scores"]["human_review_required_count"])
        self.assertEqual(
            {
                "local_synthetic_fixtures_only": True,
                "network_accessed": False,
                "github_accessed": False,
                "model_channel_used": False,
                "issue_publication_performed": False,
                "raw_fixture_content_included": False,
                "bounded_summary_only": True,
            },
            first["safety"],
        )
        serialized = json.dumps(first, sort_keys=True)
        self.assertNotIn("affected_locations", serialized)
        self.assertNotIn("remediation_property", serialized)
        self.assertNotIn("fixture_text", serialized)

    def test_report_schema_is_closed_and_pins_non_mutating_safety_contract(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "templates" / "reports" / "efficacy-benchmark.schema.json").read_text(
                encoding="utf-8"
            )
        )
        report = build_fixture_report(REPO_ROOT)

        self.assertFalse(schema["additionalProperties"])
        self.assertEqual({"const": False}, schema["properties"]["safety"]["properties"]["network_accessed"])
        self.assertEqual({"const": False}, schema["properties"]["safety"]["properties"]["github_accessed"])
        self.assertEqual(
            {"const": False},
            schema["properties"]["safety"]["properties"]["issue_publication_performed"],
        )
        validate_schema_object(report, schema, label="efficacy benchmark")
        report["raw_evidence"] = "must remain outside the contract"
        with self.assertRaisesRegex(EfficacyCorpusError, "closed corpus contract"):
            validate_schema_object(report, schema, label="efficacy benchmark")

    def test_report_schema_loader_rejects_symlinked_resource(self) -> None:
        lab_root = self.work / "lab"
        shutil.copytree(REPO_ROOT / "benchmarks", lab_root / "benchmarks")
        schema_dir = lab_root / "templates" / "reports"
        schema_dir.mkdir(parents=True)
        outside = self.work / "outside-schema.json"
        shutil.copyfile(REPO_ROOT / "templates" / "reports" / "efficacy-benchmark.schema.json", outside)
        schema_path = schema_dir / "efficacy-benchmark.schema.json"
        try:
            schema_path.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")

        with self.assertRaisesRegex(EfficacyBenchmarkError, "closed schema contract"):
            build_fixture_report(lab_root)

    def test_loader_returns_stable_declared_fixture_text_without_extra_files(self) -> None:
        first_loaded, first_texts = load_corpus_fixture_texts(REPO_ROOT)
        second_loaded, second_texts = load_corpus_fixture_texts(REPO_ROOT)

        self.assertEqual(first_loaded, second_loaded)
        self.assertEqual(first_texts, second_texts)
        declared = {
            case["case_id"]: {item["path"] for item in case["fixture"]["files"]}
            for case in first_loaded["cases"]
        }
        self.assertEqual(declared, {case_id: set(paths) for case_id, paths in first_texts.items()})

    def test_reference_rules_do_not_depend_on_case_ids_or_fixture_filenames(self) -> None:
        loaded, fixture_texts = load_corpus_fixture_texts(REPO_ROOT)
        for case in loaded["cases"]:
            original = fixture_texts[case["case_id"]]
            renamed = {
                f"renamed-{index}{Path(path).suffix}": text
                for index, (path, text) in enumerate(sorted(original.items()), start=1)
            }
            with self.subTest(case_id=case["case_id"]):
                self.assertEqual(
                    analyze_fixture_case(case, original),
                    analyze_fixture_case({**case, "case_id": "synthetic/renamed-case"}, renamed),
                )

    def test_suite_and_explicit_case_selection_are_sorted_and_fail_closed(self) -> None:
        loaded = load_corpus(REPO_ROOT)
        suite_cases, suite_selection = select_cases(loaded, suite="appsec")
        explicit_cases, explicit_selection = select_cases(
            loaded,
            case_ids=["python-web/path-001", "ai-agent-mcp/tool-control-001"],
        )

        self.assertEqual(
            [
                "execution-boundaries/query-001",
                "execution-boundaries/query-control-001",
                "python-web/authz-001",
                "python-web/authz-control-001",
                "python-web/path-001",
                "python-web/path-control-001",
                "secrets-logging/request-log-001",
                "secrets-logging/request-log-control-001",
                "webhook-trust/signature-001",
                "webhook-trust/signature-control-001",
            ],
            [case["case_id"] for case in suite_cases],
        )
        self.assertEqual("suite", suite_selection["kind"])
        self.assertEqual(
            ["ai-agent-mcp/tool-control-001", "python-web/path-001"],
            [case["case_id"] for case in explicit_cases],
        )
        self.assertEqual("cases", explicit_selection["kind"])
        with self.assertRaisesRegex(EfficacyBenchmarkError, "cannot be combined"):
            select_cases(loaded, suite="core", case_ids=["python-web/path-001"])
        with self.assertRaisesRegex(EfficacyBenchmarkError, "must be unique"):
            select_cases(loaded, case_ids=["python-web/path-001", "python-web/path-001"])
        with self.assertRaisesRegex(EfficacyBenchmarkError, "unknown efficacy benchmark case"):
            select_cases(loaded, case_ids=["python-web/missing-001"])
        with self.assertRaisesRegex(EfficacyBenchmarkError, "unknown efficacy benchmark suite"):
            select_cases(loaded, suite="missing")

    def test_scoring_records_false_positive_false_negative_and_severity_disagreement(self) -> None:
        loaded = load_corpus(REPO_ROOT)
        positive = next(case for case in loaded["cases"] if case["case_id"] == "python-web/authz-001")
        control = next(
            case for case in loaded["cases"] if case["case_id"] == "python-web/authz-control-001"
        )
        analyses = {
            positive["case_id"]: {
                "predictions": [],
                "target_covered": True,
                "rule_supported": True,
                "fixture_file_count": 1,
                "human_review_required": True,
            },
            control["case_id"]: {
                "predictions": [
                    {
                        "vulnerability_class": "missing-tenant-authorization",
                        "severity": "Low",
                        "human_review_required": True,
                    }
                ],
                "target_covered": False,
                "rule_supported": False,
                "fixture_file_count": 1,
                "human_review_required": True,
            },
        }

        scored = score_cases([positive, control], analyses)

        self.assertEqual(0, scored["counts"]["true_positives"])
        self.assertEqual(1, scored["counts"]["false_positives"])
        self.assertEqual(1, scored["counts"]["false_negatives"])
        self.assertEqual(0, scored["counts"]["true_negatives"])
        self.assertEqual(0.0, scored["rates"]["precision"])
        self.assertEqual(0.0, scored["rates"]["recall"])
        self.assertEqual(0.0, scored["rates"]["f1"])
        self.assertEqual({"covered": 1, "selected": 2, "rate": 0.5}, scored["target_coverage"])
        self.assertEqual(["false_negative", "false_positive"], [case["outcome"] for case in scored["cases"]])

    def test_cli_list_succeeds_without_external_path_tools(self) -> None:
        listed = self.run_command("--list")

        self.assertEqual(0, listed.returncode, listed.stderr)
        self.assertIn("CASE ID\tCLASS\tCATEGORY\tSUITES", listed.stdout)

    @unittest.skipUnless(
        efficacy_benchmark.DIR_FD_OUTPUT_SUPPORTED,
        "requires dirfd-anchored output support",
    )
    def test_cli_writes_byte_stable_bounded_reports_without_external_path_tools(self) -> None:
        first_json = self.work / "first.json"
        first_md = self.work / "first.md"
        second_json = self.work / "second.json"
        second_md = self.work / "second.md"
        first = self.run_command("--out-json", str(first_json), "--out-md", str(first_md))
        second = self.run_command("--out-json", str(second_json), "--out-md", str(second_md))

        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual(first_json.read_bytes(), second_json.read_bytes())
        self.assertEqual(first_md.read_bytes(), second_md.read_bytes())
        self.assertLess(len(first_json.read_bytes()), 1_000_000)
        self.assertLess(len(first_md.read_bytes()), 1_000_000)
        self.assertIn("not a product efficacy claim", first_md.read_text(encoding="utf-8"))

    @unittest.skipUnless(
        efficacy_benchmark.DIR_FD_OUTPUT_SUPPORTED,
        "requires dirfd-anchored output support",
    )
    def test_cli_selection_errors_and_output_path_safety_return_status_two(self) -> None:
        unknown = self.run_command("--suite", "missing")
        same = self.run_command("--out-json", "same", "--out-md", "same")
        alias = self.run_command("--out-json", "alias", "--out-md", "nested/../alias")

        self.assertEqual(2, unknown.returncode)
        self.assertIn("unknown efficacy benchmark suite", unknown.stderr)
        self.assertEqual(2, same.returncode)
        self.assertIn("different paths", same.stderr)
        self.assertEqual(2, alias.returncode)
        self.assertIn("different paths", alias.stderr)

        target = self.work / "target.json"
        target.write_text("{}\n", encoding="utf-8")
        link = self.work / "link.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")
        result = self.run_command("--out-json", str(link), "--out-md", str(self.work / "safe.md"))
        self.assertEqual(2, result.returncode)
        self.assertIn("non-symlink", result.stderr)
        self.assertEqual("{}\n", target.read_text(encoding="utf-8"))

    def test_write_report_rejects_unbounded_payload_before_writing(self) -> None:
        report = build_fixture_report(REPO_ROOT)
        report["limitations"] = ["x" * 1_100_000]
        json_path = self.work / "oversized.json"
        markdown_path = self.work / "oversized.md"

        with self.assertRaisesRegex(EfficacyBenchmarkError, "size limit"):
            write_report(report, json_path, markdown_path)
        self.assertFalse(json_path.exists())
        self.assertFalse(markdown_path.exists())

    @unittest.skipUnless(
        efficacy_benchmark.DIR_FD_OUTPUT_SUPPORTED,
        "requires dirfd-anchored output support",
    )
    def test_write_report_preserves_pair_when_second_stage_fails(self) -> None:
        report = build_fixture_report(REPO_ROOT)
        json_path = self.work / "result.json"
        markdown_path = self.work / "result.md"
        json_path.write_text("old json\n", encoding="utf-8")
        markdown_path.write_text("old markdown\n", encoding="utf-8")
        real_stage = efficacy_benchmark._stage_write
        calls = 0

        def fail_second(path: Path, content: str) -> efficacy_benchmark._StagedOutput:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise PermissionError("fixture second-stage failure")
            return real_stage(path, content)

        with (
            unittest.mock.patch.object(efficacy_benchmark, "_stage_write", side_effect=fail_second),
            self.assertRaisesRegex(PermissionError, "second-stage"),
        ):
            write_report(report, json_path, markdown_path)

        self.assertEqual("old json\n", json_path.read_text(encoding="utf-8"))
        self.assertEqual("old markdown\n", markdown_path.read_text(encoding="utf-8"))
        self.assertEqual([], list(self.work.glob(".*.tmp")))

    def test_report_write_fails_closed_without_dirfd_support(self) -> None:
        report = build_fixture_report(REPO_ROOT)
        json_path = self.work / "portable" / "result.json"
        markdown_path = self.work / "portable" / "result.md"

        with (
            unittest.mock.patch.object(efficacy_benchmark, "DIR_FD_OUTPUT_SUPPORTED", False),
            self.assertRaisesRegex(EfficacyBenchmarkError, "require dirfd support"),
        ):
            write_report(report, json_path, markdown_path)

        self.assertFalse(json_path.exists())
        self.assertFalse(markdown_path.exists())
        self.assertFalse(json_path.parent.exists())

    @unittest.skipUnless(
        efficacy_benchmark.DIR_FD_OUTPUT_SUPPORTED,
        "requires dirfd-anchored output support",
    )
    def test_write_report_rolls_back_pair_when_second_commit_fails(self) -> None:
        report = build_fixture_report(REPO_ROOT)
        json_path = self.work / "result.json"
        markdown_path = self.work / "result.md"
        json_path.write_text("old json\n", encoding="utf-8")
        markdown_path.write_text("old markdown\n", encoding="utf-8")
        real_rename = efficacy_benchmark.os.rename

        def fail_markdown_rename(source, destination, *args, **kwargs) -> None:
            if str(source).startswith(".result.md.") and str(source).endswith(".tmp"):
                raise PermissionError("fixture second-commit failure")
            real_rename(source, destination, *args, **kwargs)

        patch = unittest.mock.patch.object(
            efficacy_benchmark.os,
            "rename",
            side_effect=fail_markdown_rename,
        )

        with patch, self.assertRaisesRegex(PermissionError, "second-commit"):
            write_report(report, json_path, markdown_path)

        self.assertEqual("old json\n", json_path.read_text(encoding="utf-8"))
        self.assertEqual("old markdown\n", markdown_path.read_text(encoding="utf-8"))
        self.assertEqual([], list(self.work.glob(".*.tmp")))
        self.assertEqual([], list(self.work.glob(".*.backup")))

    @unittest.skipUnless(
        efficacy_benchmark.DIR_FD_OUTPUT_SUPPORTED,
        "requires dirfd-anchored output support",
    )
    def test_write_report_rejects_parent_swap_without_writing_through_symlink(self) -> None:
        report = build_fixture_report(REPO_ROOT)
        output_parent = self.work / "output"
        output_parent.mkdir()
        json_path = output_parent / "result.json"
        markdown_path = output_parent / "result.md"
        json_path.write_text("old json\n", encoding="utf-8")
        markdown_path.write_text("old markdown\n", encoding="utf-8")
        original_parent = self.work / "output-original"
        outside_parent = self.work / "outside"
        outside_parent.mkdir()
        real_commit = efficacy_benchmark._commit_staged_outputs

        def swap_then_commit(staged_outputs: list[efficacy_benchmark._StagedOutput]) -> None:
            output_parent.rename(original_parent)
            output_parent.symlink_to(outside_parent, target_is_directory=True)
            real_commit(staged_outputs)

        with (
            unittest.mock.patch.object(
                efficacy_benchmark,
                "_commit_staged_outputs",
                side_effect=swap_then_commit,
            ),
            self.assertRaisesRegex(EfficacyBenchmarkError, "output parent changed"),
        ):
            write_report(report, json_path, markdown_path)

        self.assertEqual("old json\n", (original_parent / "result.json").read_text(encoding="utf-8"))
        self.assertEqual("old markdown\n", (original_parent / "result.md").read_text(encoding="utf-8"))
        self.assertEqual([], list(original_parent.glob(".*.tmp")))
        self.assertEqual([], list(outside_parent.iterdir()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
