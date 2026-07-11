from __future__ import annotations

import os
import stat
import statistics
from pathlib import Path
from typing import Any

from efficacy_benchmark import EfficacyBenchmarkError
from efficacy_corpus import (
    EfficacyCorpusError,
    load_bounded_json_objects,
    load_schema_object,
    require_public_safe_json,
    validate_schema_object,
)


METADATA_NAME = "holdout-metadata.json"
AGGREGATE_NAME = "holdout-aggregate.json"
MAX_HOLDOUT_RECORD_BYTES = 512_000


def _absolute_non_symlink_root(
    value: Path,
    lab_root: Path,
) -> tuple[Path, tuple[int, int, int]]:
    if not value.is_absolute():
        raise EfficacyBenchmarkError("--records-root must be an absolute path")
    candidate = Path(os.path.abspath(os.fspath(value)))
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise EfficacyBenchmarkError("--records-root must be an existing readable directory") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise EfficacyBenchmarkError("--records-root must be a non-symlink directory")
    current = candidate
    while current != current.parent:
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                raise EfficacyBenchmarkError("--records-root must not contain symlink components")
        except OSError as exc:
            raise EfficacyBenchmarkError("--records-root must have readable path components") from exc
        current = current.parent
    trusted = lab_root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    if resolved != candidate:
        raise EfficacyBenchmarkError("--records-root must not contain symlink components")
    try:
        resolved.relative_to(trusted)
    except ValueError:
        pass
    else:
        raise EfficacyBenchmarkError("--records-root must stay outside packaged or tracked repository content")
    try:
        trusted.relative_to(resolved)
    except ValueError:
        pass
    else:
        raise EfficacyBenchmarkError("--records-root must not contain the package or repository root")
    verified = resolved.lstat()
    verified_identity = (verified.st_dev, verified.st_ino, verified.st_mode)
    initial_identity = (metadata.st_dev, metadata.st_ino, metadata.st_mode)
    if verified_identity != initial_identity:
        raise EfficacyBenchmarkError("--records-root changed during validation")
    return resolved, verified_identity


def _validate_metric_summary(summary: dict[str, Any], *, label: str) -> None:
    applicable = summary["applicable_run_count"]
    values = [summary[name] for name in ("minimum", "maximum", "mean", "population_variance")]
    if applicable == 0:
        if any(value is not None for value in values):
            raise EfficacyBenchmarkError(f"{label} values must be null when no runs are applicable")
        return
    if any(value is None for value in values):
        raise EfficacyBenchmarkError(f"{label} values must be numeric when runs are applicable")
    minimum, maximum, mean, _variance = values
    if minimum > maximum or not minimum <= mean <= maximum:
        raise EfficacyBenchmarkError(f"{label} minimum, mean, and maximum are inconsistent")


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _require_rate(actual: float | None, expected: float | None, *, label: str) -> None:
    if actual != expected:
        raise EfficacyBenchmarkError(f"{label} is inconsistent with its aggregate counts")


def _metric_values(runs: list[dict[str, Any]], metric: str) -> list[float]:
    if metric in {"precision", "recall", "f1"}:
        values = [run["rates"][metric] for run in runs]
    elif metric == "severity_agreement":
        values = [run["severity_agreement"]["rate"] for run in runs]
    elif metric == "target_coverage":
        values = [run["target_coverage"]["rate"] for run in runs]
    else:
        values = [run["human_review_required_count"] for run in runs]
    return [float(value) for value in values if value is not None]


def _validate_recomputed_variance(
    runs: list[dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
) -> None:
    for metric, summary in summaries.items():
        values = _metric_values(runs, metric)
        expected = {
            "applicable_run_count": len(values),
            "minimum": round(min(values), 6) if values else None,
            "maximum": round(max(values), 6) if values else None,
            "mean": round(statistics.fmean(values), 6) if values else None,
            "population_variance": round(statistics.pvariance(values), 6) if values else None,
        }
        if summary != expected:
            raise EfficacyBenchmarkError(f"repeat_variance.{metric} does not match the recorded runs")


def _validate_semantics(metadata: dict[str, Any], aggregate: dict[str, Any]) -> None:
    corpus = metadata["corpus"]
    aggregate_corpus = aggregate["corpus"]
    for name in (
        "corpus_id",
        "corpus_version",
        "case_count",
        "positive_count",
        "negative_control_count",
        "category_count",
        "balanced_controls",
        "balance_exception_record_digest",
    ):
        if corpus[name] != aggregate_corpus[name]:
            raise EfficacyBenchmarkError(f"holdout metadata and aggregate disagree on corpus.{name}")
    if corpus["positive_count"] + corpus["negative_control_count"] != corpus["case_count"]:
        raise EfficacyBenchmarkError("holdout corpus class counts must equal case_count")
    if corpus["category_count"] > corpus["case_count"]:
        raise EfficacyBenchmarkError("holdout category_count must not exceed case_count")
    balanced = corpus["positive_count"] == corpus["negative_control_count"]
    if corpus["balanced_controls"] != balanced:
        raise EfficacyBenchmarkError("holdout balanced_controls does not match the class counts")
    if balanced != (corpus["balance_exception_record_digest"] is None):
        raise EfficacyBenchmarkError("unbalanced holdout counts require a balance-exception record")
    if metadata["evaluation_plan"]["command_version"] != aggregate["command_version"]:
        raise EfficacyBenchmarkError("holdout metadata and aggregate disagree on command_version")
    if metadata["evaluation_plan"]["report_schema_version"] != aggregate["report_schema_version"]:
        raise EfficacyBenchmarkError("holdout metadata and aggregate disagree on report_schema_version")
    review = metadata["ground_truth_review"]
    if review["review_method"] == "two-person" and review["reviewer_count"] < 2:
        raise EfficacyBenchmarkError("two-person ground truth review requires at least two reviewers")
    if len(review["review_record_digests"]) != review["reviewer_count"]:
        raise EfficacyBenchmarkError("ground truth review records must match reviewer_count")

    planned = metadata["evaluation_plan"]["configurations"]
    results = aggregate["configurations"]
    plan_ids = [item["configuration_id"] for item in planned]
    result_ids = [item["configuration_id"] for item in results]
    if len(plan_ids) != len(set(plan_ids)) or len(result_ids) != len(set(result_ids)):
        raise EfficacyBenchmarkError("holdout configuration IDs must be unique")
    if plan_ids != result_ids:
        raise EfficacyBenchmarkError("holdout aggregate configurations must exactly match the evaluation plan")
    plan_by_id = {item["configuration_id"]: item for item in planned}
    result_by_id = {item["configuration_id"]: item for item in results}
    for configuration_id, plan in plan_by_id.items():
        result = result_by_id[configuration_id]
        for name in (
            "workflow_version",
            "prompt_version",
            "worker_channel_used",
            "worker_profile_id",
            "worker_cli_version",
            "model_id",
            "effort",
            "repeat_runs",
        ):
            if plan[name] != result[name]:
                raise EfficacyBenchmarkError(
                    f"holdout plan and aggregate disagree on {configuration_id}.{name}"
                )
        worker_fields = (
            plan["worker_profile_id"],
            plan["worker_cli_version"],
            plan["model_id"],
            plan["effort"],
        )
        if plan["worker_channel_used"] and any(value is None for value in worker_fields):
            raise EfficacyBenchmarkError(
                "worker configurations require profile, CLI, model, and effort identifiers"
            )
        if not plan["worker_channel_used"] and any(value is not None for value in worker_fields):
            raise EfficacyBenchmarkError("non-worker configurations must not record worker identifiers")
        if len(result["runs"]) != plan["repeat_runs"]:
            raise EfficacyBenchmarkError("holdout run count must match the fixed evaluation plan")
        expected_numbers = list(range(1, plan["repeat_runs"] + 1))
        if [run["run_number"] for run in result["runs"]] != expected_numbers:
            raise EfficacyBenchmarkError("holdout run numbers must be contiguous and ordered")
        for run in result["runs"]:
            counts = run["counts"]
            if run["evaluated_negative_control_count"] != corpus["negative_control_count"]:
                raise EfficacyBenchmarkError("every holdout negative control must be evaluated")
            if counts["true_positives"] + counts["false_negatives"] != corpus["positive_count"]:
                raise EfficacyBenchmarkError("holdout TP and FN must equal the positive case count")
            if counts["true_negatives"] > corpus["negative_control_count"]:
                raise EfficacyBenchmarkError("holdout TN exceeds the negative-control count")
            false_positive_controls = run["negative_control_false_positive_case_count"]
            if (
                counts["true_negatives"] + false_positive_controls
                != run["evaluated_negative_control_count"]
                or false_positive_controls > counts["false_positives"]
            ):
                raise EfficacyBenchmarkError("holdout negative-control outcomes are incomplete")
            if counts["prediction_count"] != counts["true_positives"] + counts["false_positives"]:
                raise EfficacyBenchmarkError("holdout prediction_count must equal TP plus FP")
            rates = run["rates"]
            precision = _rate(
                counts["true_positives"],
                counts["true_positives"] + counts["false_positives"],
            )
            recall = _rate(
                counts["true_positives"],
                counts["true_positives"] + counts["false_negatives"],
            )
            f1 = (
                None
                if precision is None or recall is None or precision + recall == 0
                else round(2 * precision * recall / (precision + recall), 6)
            )
            _require_rate(rates["precision"], precision, label="holdout precision")
            _require_rate(rates["recall"], recall, label="holdout recall")
            _require_rate(rates["f1"], f1, label="holdout F1")
            severity = run["severity_agreement"]
            if severity["agreed"] > severity["eligible"] or severity["eligible"] > counts["true_positives"]:
                raise EfficacyBenchmarkError("holdout severity agreement counts are inconsistent")
            _require_rate(
                severity["rate"],
                _rate(severity["agreed"], severity["eligible"]),
                label="holdout severity agreement rate",
            )
            coverage = run["target_coverage"]
            if coverage["selected"] != corpus["case_count"] or coverage["covered"] > coverage["selected"]:
                raise EfficacyBenchmarkError("holdout target coverage is inconsistent with corpus size")
            _require_rate(
                coverage["rate"],
                _rate(coverage["covered"], coverage["selected"]),
                label="holdout target coverage rate",
            )
            if run["human_review_required_count"] > corpus["case_count"]:
                raise EfficacyBenchmarkError("holdout human review count exceeds corpus size")
        for metric, summary in result["repeat_variance"].items():
            _validate_metric_summary(summary, label=f"repeat_variance.{metric}")
            if summary["applicable_run_count"] > plan["repeat_runs"]:
                raise EfficacyBenchmarkError("repeat variance applicable count exceeds repeat_runs")
        _validate_recomputed_variance(result["runs"], result["repeat_variance"])

    adjudication = aggregate["adjudication"]
    if not (
        adjudication["changed_ground_truth_count"]
        <= adjudication["disputed_case_count"]
        <= corpus["case_count"]
    ):
        raise EfficacyBenchmarkError("holdout adjudication counts are inconsistent")

    publication = aggregate["publication"]
    if publication["approved"] != (publication["approval_record_digest"] is not None):
        raise EfficacyBenchmarkError("publication approval and approval record digest must be recorded together")


def load_and_validate_holdout_records(lab_root: Path, records_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root, root_identity = _absolute_non_symlink_root(records_root, lab_root)
    try:
        metadata, aggregate = load_bounded_json_objects(
            root,
            (
                (METADATA_NAME, "private holdout metadata", MAX_HOLDOUT_RECORD_BYTES),
                (AGGREGATE_NAME, "private holdout aggregate", MAX_HOLDOUT_RECORD_BYTES),
            ),
            expected_root_identity=root_identity,
        )
        metadata_schema = load_schema_object(
            lab_root,
            "templates/reports/efficacy-holdout-metadata.schema.json",
            label="private holdout metadata schema",
        )
        aggregate_schema = load_schema_object(
            lab_root,
            "templates/reports/efficacy-holdout-aggregate.schema.json",
            label="private holdout aggregate schema",
        )
        validate_schema_object(metadata, metadata_schema, label="private holdout metadata")
        validate_schema_object(aggregate, aggregate_schema, label="private holdout aggregate")
        require_public_safe_json(metadata, label="private holdout metadata")
        require_public_safe_json(aggregate, label="private holdout aggregate")
    except EfficacyCorpusError as exc:
        raise EfficacyBenchmarkError(str(exc)) from exc
    _validate_semantics(metadata, aggregate)
    return metadata, aggregate


def render_holdout_summary(metadata: dict[str, Any], aggregate: dict[str, Any]) -> str:
    corpus = metadata["corpus"]
    repeat_counts = [item["repeat_runs"] for item in aggregate["configurations"]]
    return "\n".join(
        [
            "Private holdout records validated",
            f"Corpus: {corpus['corpus_id']} {corpus['corpus_version']}",
            (
                f"Cases: {corpus['case_count']} "
                f"(positive={corpus['positive_count']}, controls={corpus['negative_control_count']})"
            ),
            f"Configurations: {len(aggregate['configurations'])}",
            f"Repeat runs: {min(repeat_counts)}-{max(repeat_counts)}",
            f"Publication approved: {str(aggregate['publication']['approved']).lower()}",
        ]
    ) + "\n"
