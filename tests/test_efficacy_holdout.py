from __future__ import annotations

import contextlib
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMMAND = REPO_ROOT / "bin" / "gra-efficacy-holdout"
sys.path.insert(0, str(REPO_ROOT / "lib"))

from efficacy_benchmark import EfficacyBenchmarkError  # noqa: E402
from efficacy_holdout import load_and_validate_holdout_records, render_holdout_summary  # noqa: E402
import efficacy_holdout  # noqa: E402


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
DIGEST_D = "d" * 64


def metric_summary(value: float) -> dict:
    return {
        "applicable_run_count": 2,
        "minimum": value,
        "maximum": value,
        "mean": value,
        "population_variance": 0,
    }


def records() -> tuple[dict, dict]:
    corpus = {
        "corpus_id": "holdout-012345abcdef",
        "corpus_version": f"1.0.0+sha256.{DIGEST_A}",
        "case_count": 4,
        "positive_count": 2,
        "negative_control_count": 2,
        "category_count": 2,
        "balanced_controls": True,
        "balance_exception_record_digest": None,
    }
    configuration = {
        "configuration_id": "config-012345abcdef",
        "workflow_version": f"sha256:{DIGEST_B}",
        "prompt_version": f"sha256:{DIGEST_C}",
        "worker_channel_used": False,
        "worker_profile_id": None,
        "worker_cli_version": None,
        "model_id": None,
        "effort": None,
        "repeat_runs": 2,
    }
    metadata = {
        "schema_version": "1",
        "corpus": corpus,
        "separation": {
            "private_not_tracked": True,
            "public_corpus_reused": False,
            "real_repository_content_included": False,
            "storage_access_controlled": True,
        },
        "ground_truth_review": {
            "review_method": "two-person",
            "reviewer_count": 2,
            "independent_from_evaluation": True,
            "completed": True,
            "review_record_digests": [f"sha256:{DIGEST_A}", f"sha256:{DIGEST_B}"],
        },
        "evaluation_plan": {
            "command_version": "0.4.0",
            "report_schema_version": "1",
            "adjudication_required": True,
            "configurations": [configuration],
        },
    }
    run = {
        "run_number": 1,
        "evaluated_negative_control_count": 2,
        "negative_control_false_positive_case_count": 0,
        "counts": {
            "true_positives": 2,
            "false_positives": 0,
            "false_negatives": 0,
            "true_negatives": 2,
            "prediction_count": 2,
        },
        "rates": {"precision": 1, "recall": 1, "f1": 1},
        "severity_agreement": {"agreed": 2, "eligible": 2, "rate": 1},
        "target_coverage": {"covered": 4, "selected": 4, "rate": 1},
        "human_review_required_count": 2,
    }
    second_run = copy.deepcopy(run)
    second_run["run_number"] = 2
    aggregate = {
        "schema_version": "1",
        "evaluation_id": "evaluation-fedcba543210",
        "command_version": "0.4.0",
        "report_schema_version": "1",
        "corpus": copy.deepcopy(corpus),
        "configurations": [
            {
                **copy.deepcopy(configuration),
                "runs": [run, second_run],
                "repeat_variance": {
                    "precision": metric_summary(1),
                    "recall": metric_summary(1),
                    "f1": metric_summary(1),
                    "severity_agreement": metric_summary(1),
                    "target_coverage": metric_summary(1),
                    "human_review_required_count": metric_summary(2),
                },
            }
        ],
        "adjudication": {
            "completed": True,
            "disputed_case_count": 0,
            "changed_ground_truth_count": 0,
            "record_digest": f"sha256:{DIGEST_D}",
        },
        "safety": {
            "aggregate_only": True,
            "fixture_text_included": False,
            "case_ids_included": False,
            "evidence_or_locations_included": False,
            "prompts_or_transcripts_included": False,
            "credentials_included": False,
            "absolute_paths_included": False,
            "finding_publication_performed": False,
        },
        "publication": {
            "approved": False,
            "approval_record_digest": None,
            "public_claim_allowed": False,
            "production_performance_claim_allowed": False,
            "finding_publication_authorized": False,
        },
    }
    return metadata, aggregate


class EfficacyHoldoutTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        parent = REPO_ROOT.parent / ".test-tmp"
        parent.mkdir(exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix=f"holdout-{self._testMethodName}-", dir=parent))
        self.records_root = self.work / "records"
        self.records_root.mkdir(mode=0o700)
        self.metadata, self.aggregate = records()
        self.write_records()

    def tearDown(self) -> None:
        parent = self.work.parent
        shutil.rmtree(self.work, ignore_errors=True)
        with contextlib.suppress(OSError):
            parent.rmdir()

    def write_records(self) -> None:
        (self.records_root / "holdout-metadata.json").write_text(
            json.dumps(self.metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (self.records_root / "holdout-aggregate.json").write_text(
            json.dumps(self.aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def run_command(self, root: Path | str | None = None) -> subprocess.CompletedProcess[str]:
        selected = self.records_root if root is None else root
        return subprocess.run(
            [sys.executable, COMMAND, "--records-root", os.fspath(selected)],
            cwd=REPO_ROOT,
            env={**os.environ, "PATH": os.fspath(self.work / "empty-path")},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )

    def test_valid_aggregate_only_records_are_accepted_without_echoing_paths_or_private_fields(self) -> None:
        loaded_metadata, loaded_aggregate = load_and_validate_holdout_records(REPO_ROOT, self.records_root)
        summary = render_holdout_summary(loaded_metadata, loaded_aggregate)
        completed = self.run_command()

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(summary, completed.stdout)
        self.assertEqual("", completed.stderr)
        self.assertIn("Cases: 4 (positive=2, controls=2)", summary)
        self.assertNotIn(os.fspath(self.records_root), summary)
        for prohibited in ("fixture", "evidence", "location", "prompt", "transcript", "credential"):
            self.assertNotIn(prohibited, summary.lower())

    def test_root_must_be_absolute_external_and_free_of_symlink_components(self) -> None:
        relative = self.run_command("relative-records")
        inside_root = REPO_ROOT / ".test-tmp" / f"holdout-inside-{self._testMethodName}"
        inside_root.mkdir(parents=True)
        inside = self.run_command(inside_root)
        shutil.rmtree(inside_root)
        with contextlib.suppress(OSError):
            inside_root.parent.rmdir()
        linked = self.work / "linked"
        linked.symlink_to(self.records_root, target_is_directory=True)
        symlinked = self.run_command(linked)

        self.assertEqual(2, relative.returncode)
        self.assertIn("absolute path", relative.stderr)
        self.assertEqual(2, inside.returncode)
        self.assertIn("outside packaged or tracked", inside.stderr)
        self.assertEqual(2, symlinked.returncode)
        self.assertIn("non-symlink directory", symlinked.stderr)

    def test_closed_schemas_reject_leakage_fields_malformed_and_oversized_records(self) -> None:
        self.aggregate["fixture_text"] = "private fixture"
        self.write_records()
        with self.assertRaisesRegex(EfficacyBenchmarkError, "closed corpus contract"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

        self.aggregate = records()[1]
        self.write_records()
        (self.records_root / "holdout-aggregate.json").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(EfficacyBenchmarkError, "valid UTF-8 JSON"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

        (self.records_root / "holdout-aggregate.json").write_bytes(b" " * 512_001)
        with self.assertRaisesRegex(EfficacyBenchmarkError, "512000-byte limit"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

    def test_plan_run_worker_and_publication_semantics_fail_closed(self) -> None:
        self.aggregate["corpus"]["case_count"] = 5
        self.write_records()
        with self.assertRaisesRegex(EfficacyBenchmarkError, "disagree on corpus.case_count"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

        self.metadata, self.aggregate = records()
        self.metadata["evaluation_plan"]["configurations"][0]["repeat_runs"] = 3
        self.aggregate["configurations"][0]["repeat_runs"] = 3
        self.write_records()
        with self.assertRaisesRegex(EfficacyBenchmarkError, "run count"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

        self.metadata, self.aggregate = records()
        self.metadata["evaluation_plan"]["configurations"][0]["worker_channel_used"] = True
        self.aggregate["configurations"][0]["worker_channel_used"] = True
        self.write_records()
        with self.assertRaisesRegex(EfficacyBenchmarkError, "require profile, CLI, model, and effort"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

        self.metadata, self.aggregate = records()
        self.aggregate["publication"]["approved"] = True
        self.write_records()
        with self.assertRaisesRegex(EfficacyBenchmarkError, "recorded together"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

    def test_independent_review_counts_and_repeat_variance_fail_closed(self) -> None:
        self.metadata["ground_truth_review"]["reviewer_count"] = 1
        self.write_records()
        with self.assertRaisesRegex(EfficacyBenchmarkError, "at least two reviewers"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

        self.metadata, self.aggregate = records()
        summary = self.aggregate["configurations"][0]["repeat_variance"]["precision"]
        summary["minimum"] = 1
        summary["mean"] = 0.5
        self.write_records()
        with self.assertRaisesRegex(EfficacyBenchmarkError, "minimum, mean, and maximum"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

        self.metadata, self.aggregate = records()
        self.aggregate["configurations"][0]["runs"][0]["rates"]["precision"] = 0.5
        self.write_records()
        with self.assertRaisesRegex(EfficacyBenchmarkError, "precision is inconsistent"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

    def test_unbalanced_controls_require_an_external_exception_record(self) -> None:
        for document in (self.metadata, self.aggregate):
            document["corpus"]["positive_count"] = 3
            document["corpus"]["negative_control_count"] = 1
            document["corpus"]["balanced_controls"] = False
        for run in self.aggregate["configurations"][0]["runs"]:
            run["evaluated_negative_control_count"] = 1
            run["negative_control_false_positive_case_count"] = 0
            run["counts"]["true_positives"] = 3
            run["counts"]["prediction_count"] = 3
            run["counts"]["true_negatives"] = 1
            run["severity_agreement"] = {"agreed": 3, "eligible": 3, "rate": 1}
            run["human_review_required_count"] = 3
        self.aggregate["configurations"][0]["repeat_variance"]["human_review_required_count"] = metric_summary(3)
        self.write_records()
        with self.assertRaisesRegex(EfficacyBenchmarkError, "balance-exception"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

        for document in (self.metadata, self.aggregate):
            document["corpus"]["balance_exception_record_digest"] = f"sha256:{DIGEST_D}"
        self.write_records()
        load_and_validate_holdout_records(REPO_ROOT, self.records_root)

    def test_every_negative_control_must_be_evaluated_and_adjudication_counts_must_align(self) -> None:
        for run in self.aggregate["configurations"][0]["runs"]:
            run["evaluated_negative_control_count"] = 2
            run["counts"]["true_negatives"] = 0
        self.write_records()
        with self.assertRaisesRegex(EfficacyBenchmarkError, "negative-control outcomes are incomplete"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

        self.metadata, self.aggregate = records()
        self.aggregate["adjudication"]["disputed_case_count"] = 4
        self.aggregate["adjudication"]["changed_ground_truth_count"] = 5
        self.write_records()
        with self.assertRaisesRegex(EfficacyBenchmarkError, "adjudication counts"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

    def test_record_files_and_components_must_not_be_symlinks(self) -> None:
        aggregate_path = self.records_root / "holdout-aggregate.json"
        real_path = self.work / "aggregate.json"
        aggregate_path.replace(real_path)
        aggregate_path.symlink_to(real_path)
        with self.assertRaisesRegex(EfficacyBenchmarkError, "without symlink components"):
            load_and_validate_holdout_records(REPO_ROOT, self.records_root)

    def test_root_identity_is_pinned_across_validation_and_bounded_reads(self) -> None:
        original = efficacy_holdout._absolute_non_symlink_root
        retained = self.work / "retained-records"
        replacement = self.work / "replacement-records"
        shutil.copytree(self.records_root, replacement)

        def swap_after_validation(value: Path, lab_root: Path):
            validated = original(value, lab_root)
            self.records_root.rename(retained)
            self.records_root.symlink_to(replacement, target_is_directory=True)
            return validated

        with unittest.mock.patch.object(
            efficacy_holdout,
            "_absolute_non_symlink_root",
            side_effect=swap_after_validation,
        ):
            with self.assertRaisesRegex(EfficacyBenchmarkError, "root changed after validation"):
                load_and_validate_holdout_records(REPO_ROOT, self.records_root)

    def test_credential_like_identifiers_fail_closed_despite_safety_flags(self) -> None:
        identifiers = (
            "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "gho_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ghs_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ghu_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ghr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "github_pat_aaaaaaaaaaaaaaaaaaaaaaaa",
            "glpat-aaaaaaaaaaaaaaaaaaaaaaaa",
            "xoxb-aaaaaaaaaaaaaaaaaaaaaaaa",
            "sk-aaaaaaaaaaaaaaaaaaaaaaaa",
            "sk-proj-aaaaaaaaaaaaaaaaaaaaaaaa",
            "".join(("sk", "_live_", "a" * 24)),
            "".join(("rk", "_live_", "a" * 24)),
            "npm_aaaaaaaaaaaaaaaaaaaaaaaa",
            "pypi-aaaaaaaaaaaaaaaaaaaaaaaa",
            "AKIAABCDEFGHIJKLMNOP",
            "ASIAABCDEFGHIJKLMNOP",
        )
        for identifier in identifiers:
            with self.subTest(identifier=identifier):
                self.metadata, self.aggregate = records()
                for configuration in (
                    self.metadata["evaluation_plan"]["configurations"][0],
                    self.aggregate["configurations"][0],
                ):
                    configuration.update(
                        {
                            "worker_channel_used": True,
                            "worker_profile_id": "codex-cli",
                            "worker_cli_version": "0.135.0",
                            "model_id": identifier,
                            "effort": "high",
                        }
                    )
                self.write_records()
                with self.assertRaisesRegex(EfficacyBenchmarkError, "credential"):
                    load_and_validate_holdout_records(REPO_ROOT, self.records_root)

    def test_private_holdout_record_names_are_excluded_from_source_and_release_artifacts(self) -> None:
        manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        self.assertIn("prune holdout", manifest)
        self.assertIn("prune private-holdout", manifest)
        self.assertIn("global-exclude holdout-metadata.json holdout-aggregate.json", manifest)
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("holdout-metadata.json", gitignore)
        self.assertIn("holdout-aggregate.json", gitignore)

    def test_english_and_japanese_disposable_examples_match_and_validate(self) -> None:
        documents = [
            (REPO_ROOT / "docs" / "PRIVATE_HOLDOUT_PROTOCOL.md").read_text(encoding="utf-8"),
            (REPO_ROOT / "docs" / "ja" / "PRIVATE_HOLDOUT_PROTOCOL.ja.md").read_text(encoding="utf-8"),
        ]
        parsed = []
        for document in documents:
            records = re.findall(
                r"cat > \"\$RECORDS_ROOT/holdout-(metadata|aggregate)\.json\" <<'JSON'\n(.*?)\nJSON",
                document,
                flags=re.DOTALL,
            )
            self.assertEqual(["metadata", "aggregate"], [name for name, _body in records])
            parsed.append([json.loads(body) for _name, body in records])
        self.assertEqual(parsed[0], parsed[1])

        self.metadata, self.aggregate = parsed[0]
        self.write_records()
        load_and_validate_holdout_records(REPO_ROOT, self.records_root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
