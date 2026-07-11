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

from efficacy_benchmark import DIR_FD_OUTPUT_SUPPORTED, EfficacyBenchmarkError, select_cases  # noqa: E402
from efficacy_comparison import (  # noqa: E402
    build_comparison_report,
    list_configurations,
    select_configurations,
)
from efficacy_corpus import load_corpus_fixture_texts  # noqa: E402
from efficacy_worker import _validate_worker_response, _worker_base, run_worker_configuration  # noqa: E402


class EfficacyComparisonTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        parent = REPO_ROOT / ".test-tmp"
        parent.mkdir(exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)
        with contextlib.suppress(OSError):
            (REPO_ROOT / ".test-tmp").rmdir()

    def run_command(self, *args: str, path: str | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATH"] = path if path is not None else str(self.work / "empty-path")
        return subprocess.run(
            [sys.executable, COMMAND, *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def selected_cases(self, suite: str = "appsec"):
        loaded, fixture_texts = load_corpus_fixture_texts(REPO_ROOT)
        cases, _selection = select_cases(loaded, suite=suite)
        return cases, fixture_texts

    def test_default_comparison_is_deterministic_and_identifies_configurations_and_cases(self) -> None:
        first = build_comparison_report(REPO_ROOT)
        second = build_comparison_report(REPO_ROOT)

        self.assertEqual(first, second)
        self.assertEqual("deterministic-comparison", first["mode"])
        self.assertEqual(
            ["reference-review-all-signals-v1", "reference-review-high-severity-gate-v1"],
            [item["configuration_id"] for item in first["configurations"]],
        )
        complete, high = first["configurations"]
        self.assertEqual(["fixture-reference-review"], complete["workflow_stage_ids"])
        self.assertEqual(
            ["fixture-reference-review", "high-severity-review-gate"],
            high["workflow_stage_ids"],
        )
        self.assertEqual(5, complete["scores"]["counts"]["true_positives"])
        self.assertEqual(0, complete["scores"]["counts"]["false_negatives"])
        self.assertEqual(3, high["scores"]["counts"]["true_positives"])
        self.assertEqual(2, high["scores"]["counts"]["false_negatives"])
        self.assertEqual(0.6, high["scores"]["rates"]["recall"])
        self.assertEqual(-2, first["comparison"]["deltas"][0]["true_positive_delta"])
        self.assertEqual(2, first["comparison"]["deltas"][0]["false_negative_delta"])
        self.assertEqual(first["comparison"]["case_ids"], complete["case_ids"])
        self.assertEqual(first["comparison"]["case_ids"], high["case_ids"])
        self.assertFalse(first["safety"]["model_channel_used"])
        self.assertFalse(first["safety"]["external_network_beyond_model_channel_enabled"])
        self.assertFalse(first["claim_guardrails"]["product_capability_claim_allowed"])
        self.assertFalse(first["claim_guardrails"]["production_performance_claim_allowed"])
        self.assertTrue(first["claim_guardrails"]["publication_requires_human_review"])
        serialized = json.dumps(first, sort_keys=True)
        for prohibited in ("fixture_files", "affected_locations", "remediation_property", "exploit_steps"):
            self.assertNotIn(prohibited, serialized)

    def test_configuration_listing_and_selection_fail_closed(self) -> None:
        listing = list_configurations()
        self.assertIn("reference-review-all-signals-v1\tyes", listing)
        self.assertIn("reference-review-high-severity-gate-v1\tyes", listing)
        self.assertNotIn("worker:", listing)
        self.assertEqual(
            ["reference-review-all-signals-v1", "reference-review-high-severity-gate-v1"],
            select_configurations(None),
        )
        caller_order = [
            "reference-review-high-severity-gate-v1",
            "reference-review-all-signals-v1",
        ]
        self.assertEqual(caller_order, select_configurations(caller_order))
        ordered_report = build_comparison_report(REPO_ROOT, configuration_ids=caller_order)
        self.assertEqual(caller_order[0], ordered_report["comparison"]["baseline_configuration_id"])
        self.assertEqual(
            caller_order,
            [item["configuration_id"] for item in ordered_report["configurations"]],
        )
        self.assertEqual(2, ordered_report["comparison"]["deltas"][0]["true_positive_delta"])
        with self.assertRaisesRegex(EfficacyBenchmarkError, "at least two"):
            select_configurations(["reference-review-all-signals-v1"])
        with self.assertRaisesRegex(EfficacyBenchmarkError, "must be unique"):
            select_configurations(["reference-review-all-signals-v1", "reference-review-all-signals-v1"])
        with self.assertRaisesRegex(EfficacyBenchmarkError, "unknown efficacy comparison"):
            select_configurations(["reference-review-all-signals-v1", "unknown-v1"])

    def test_worker_options_require_explicit_compare_and_worker_opt_in(self) -> None:
        worker_without_compare = self.run_command("--worker", "--worker-dir", str(self.work))
        worker_option_without_opt_in = self.run_command("--compare", "--worker-dir", str(self.work))
        zero_timeout_without_opt_in = self.run_command("--compare", "--worker-timeout", "0")
        conflicting_actions = self.run_command("--list", "--compare")
        invalid_worker_timeout = self.run_command(
            "--compare",
            "--worker",
            "--worker-dir",
            str(self.work),
            "--worker-timeout",
            "0",
        )
        configuration_without_compare = self.run_command(
            "--configuration",
            "reference-review-all-signals-v1",
        )

        self.assertEqual(2, worker_without_compare.returncode)
        self.assertIn("--worker requires --compare", worker_without_compare.stderr)
        self.assertEqual(2, worker_option_without_opt_in.returncode)
        self.assertIn("require explicit --worker opt-in", worker_option_without_opt_in.stderr)
        self.assertEqual(2, zero_timeout_without_opt_in.returncode)
        self.assertIn("require explicit --worker opt-in", zero_timeout_without_opt_in.stderr)
        self.assertEqual(2, conflicting_actions.returncode)
        self.assertIn("not allowed with argument", conflicting_actions.stderr)
        self.assertEqual(2, invalid_worker_timeout.returncode)
        self.assertIn("between 30 and 3600", invalid_worker_timeout.stderr)
        self.assertEqual(2, configuration_without_compare.returncode)
        self.assertIn("--configuration requires --compare", configuration_without_compare.stderr)

    @unittest.skipUnless(
        DIR_FD_OUTPUT_SUPPORTED,
        "requires dirfd-anchored output support",
    )
    def test_cli_comparison_reports_are_byte_stable_without_external_tools(self) -> None:
        first_json = self.work / "first.json"
        first_md = self.work / "first.md"
        second_json = self.work / "second.json"
        second_md = self.work / "second.md"

        first = self.run_command("--compare", "--out-json", str(first_json), "--out-md", str(first_md))
        second = self.run_command("--compare", "--out-json", str(second_json), "--out-md", str(second_md))

        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual(first_json.read_bytes(), second_json.read_bytes())
        self.assertEqual(first_md.read_bytes(), second_md.read_bytes())
        self.assertIn("Product capability claim allowed: `false`", first_md.read_text(encoding="utf-8"))

    def make_fake_worker(self, *, version: str = "0.135.0") -> Path:
        mock_bin = self.work / "mock-bin"
        mock_bin.mkdir()
        executable = mock_bin / "codex"
        executable.write_text(
            """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
if args == ['--version']:
    print('codex-cli VERSION_PLACEHOLDER')
    raise SystemExit(0)
workspace = Path(args[args.index('--cd') + 1])
os.chdir(workspace)
Path('args.json').write_text(json.dumps(sys.argv), encoding='utf-8')
Path('environment.json').write_text(json.dumps(sorted(os.environ)), encoding='utf-8')
prompt = sys.stdin.read()
Path('captured-prompt.txt').write_text(prompt, encoding='utf-8')
payload = json.loads(prompt.split('INPUT:\\n', 1)[1])
known = {
    'python-web/authz-001': ('missing-tenant-authorization', 'High'),
    'python-web/path-001': ('unsafe-path-normalization', 'Medium'),
}
response = {'schema_version': '1', 'cases': []}
for case in payload['cases']:
    signal = known.get(case['case_id'])
    predictions = [] if signal is None else [{
        'vulnerability_class': signal[0],
        'severity': signal[1],
        'human_review_required': True,
    }]
    response['cases'].append({
        'case_id': case['case_id'],
        'predictions': predictions,
        'target_covered': True,
        'human_review_required': bool(predictions),
    })
output = Path(args[args.index('--output-last-message') + 1])
output.write_text(json.dumps(response), encoding='utf-8')
print(json.dumps({'type': 'result', 'status': 'ok'}))
""",
            encoding="utf-8",
        )
        executable.write_text(
            executable.read_text(encoding="utf-8").replace("VERSION_PLACEHOLDER", version),
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return mock_bin

    def test_worker_execution_is_explicit_read_only_network_denied_and_bounded(self) -> None:
        cases, fixture_texts = self.selected_cases()
        worker_base = self.work / "worker-base"
        worker_base.mkdir()
        mock_bin = self.make_fake_worker()
        path = f"{mock_bin}{os.pathsep}{os.environ.get('PATH', '')}"

        with unittest.mock.patch.dict(
            os.environ,
            {
                "PATH": path,
                "GH_TOKEN": "must-not-reach-worker",
                "AWS_SECRET_ACCESS_KEY": "must-not-reach-worker",
                "OPENAI_API_KEY": "required-model-auth",
            },
        ):
            worker = run_worker_configuration(
                REPO_ROOT,
                cases=cases,
                fixture_texts=fixture_texts,
                worker_dir=worker_base,
                profile_id="codex-cli",
                model="fixture-model",
                effort="medium",
                timeout_seconds=60,
            )

        args = json.loads((worker["artifacts_dir"] / "args.json").read_text(encoding="utf-8"))
        environment_names = json.loads(
            (worker["artifacts_dir"] / "environment.json").read_text(encoding="utf-8")
        )
        self.assertTrue(Path(args[0]).is_absolute())
        self.assertNotIn("GH_TOKEN", environment_names)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment_names)
        self.assertIn("OPENAI_API_KEY", environment_names)
        prompt = (worker["artifacts_dir"] / "captured-prompt.txt").read_text(encoding="utf-8")
        self.assertEqual("read-only", args[args.index("--sandbox") + 1])
        self.assertIn('approval_policy="never"', args)
        self.assertIn('web_search="disabled"', args)
        self.assertIn("sandbox_workspace_write.network_access=false", args)
        self.assertIn("--ephemeral", args)
        self.assertIn("--ignore-user-config", args)
        self.assertIn("--ignore-rules", args)
        self.assertEqual("response-schema.json", args[args.index("--output-schema") + 1])
        self.assertTrue((worker["artifacts_dir"] / "response-schema.json").is_file())
        self.assertNotIn("ground_truth", prompt)
        self.assertNotIn("remediation_property", prompt)
        self.assertIn("defensive-synthetic-fixture-classification", prompt)
        self.assertFalse(worker["sandbox_network_enabled"])

        report = build_comparison_report(REPO_ROOT, suite="appsec", worker_result=worker)
        self.assertEqual("worker-assisted-comparison", report["mode"])
        self.assertTrue(report["safety"]["model_channel_used"])
        self.assertFalse(report["safety"]["external_network_beyond_model_channel_enabled"])
        self.assertFalse(report["safety"]["worker_user_configuration_loaded"])
        self.assertFalse(report["safety"]["worker_project_rules_loaded"])
        self.assertEqual("worker:codex-cli", report["configurations"][-1]["configuration_id"])
        self.assertEqual(["worker-fixture-review"], report["configurations"][-1]["workflow_stage_ids"])
        self.assertEqual("medium", report["configurations"][-1]["worker_effort"])
        self.assertEqual("0.135.0", report["configurations"][-1]["worker_cli_version"])
        self.assertFalse(report["configurations"][-1]["deterministic"])
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn("fixture_files", serialized)
        self.assertNotIn("captured-prompt", serialized)
        self.assertNotIn(str(worker["artifacts_dir"]), serialized)

    @unittest.skipUnless(
        DIR_FD_OUTPUT_SUPPORTED,
        "requires dirfd-anchored output support",
    )
    def test_cli_worker_comparison_runs_only_after_explicit_opt_in(self) -> None:
        worker_base = self.work / "worker-base"
        worker_base.mkdir()
        mock_bin = self.make_fake_worker()
        path = f"{mock_bin}{os.pathsep}{os.environ.get('PATH', '')}"
        json_path = self.work / "worker-comparison.json"
        markdown_path = self.work / "worker-comparison.md"

        completed = self.run_command(
            "--compare",
            "--suite",
            "appsec",
            "--worker",
            "--worker-dir",
            str(worker_base),
            "--model",
            "fixture-model",
            "--effort",
            "medium",
            "--out-json",
            str(json_path),
            "--out-md",
            str(markdown_path),
            path=path,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("Configurations: 3", completed.stdout)
        self.assertIn("Model channel used: true", completed.stdout)
        report = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual("worker-assisted-comparison", report["mode"])
        self.assertEqual("worker:codex-cli", report["configurations"][-1]["configuration_id"])
        self.assertEqual(1, len(list(worker_base.glob("run-*"))))

    def test_worker_response_and_directory_contracts_fail_closed(self) -> None:
        cases, _fixture_texts = self.selected_cases()
        valid_cases = [
            {
                "case_id": case["case_id"],
                "predictions": [],
                "target_covered": True,
                "human_review_required": False,
            }
            for case in cases
        ]
        invalid = {"schema_version": "1", "cases": valid_cases, "raw_evidence": "not allowed"}
        with self.assertRaisesRegex(EfficacyBenchmarkError, "closed schema contract"):
            _validate_worker_response(REPO_ROOT, json.dumps(invalid).encode(), cases)

        reordered = {"schema_version": "1", "cases": list(reversed(valid_cases))}
        with self.assertRaisesRegex(EfficacyBenchmarkError, "exactly match"):
            _validate_worker_response(REPO_ROOT, json.dumps(reordered).encode(), cases)

        with self.assertRaisesRegex(EfficacyBenchmarkError, "exactly match"):
            build_comparison_report(
                REPO_ROOT,
                suite="appsec",
                worker_result={
                    "profile_id": "codex-cli",
                    "model_id": "fixture-model",
                    "effort": "medium",
                    "codex_cli_version": "0.135.0",
                    "analyses": {},
                },
            )

        outside = REPO_ROOT.parent / "outside-worker-dir"
        with self.assertRaisesRegex(EfficacyBenchmarkError, "current working directory"):
            _worker_base(outside)

    def test_worker_rejects_codex_cli_older_than_the_isolated_execution_contract(self) -> None:
        cases, fixture_texts = self.selected_cases()
        worker_base = self.work / "worker-base"
        worker_base.mkdir()
        mock_bin = self.make_fake_worker(version="0.134.0")
        path = f"{mock_bin}{os.pathsep}{os.environ.get('PATH', '')}"

        with unittest.mock.patch.dict(os.environ, {"PATH": path}):
            with self.assertRaisesRegex(EfficacyBenchmarkError, "0.135.0 or newer"):
                run_worker_configuration(
                    REPO_ROOT,
                    cases=cases,
                    fixture_texts=fixture_texts,
                    worker_dir=worker_base,
                    profile_id="codex-cli",
                    model="fixture-model",
                    effort="medium",
                    timeout_seconds=60,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
