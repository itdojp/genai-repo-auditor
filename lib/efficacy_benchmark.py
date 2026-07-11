from __future__ import annotations

import contextlib
import json
import os
import stat
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from efficacy_corpus import (
    EfficacyCorpusError,
    load_corpus_fixture_texts,
    load_schema_object,
    validate_schema_object,
)


REPORT_SCHEMA_VERSION = "1"
DETECTOR_ID = "synthetic-reference-rules-v1"
MAX_REPORT_BYTES = 1_000_000
DIR_FD_OUTPUT_SUPPORTED = (
    os.open in os.supports_dir_fd
    and os.mkdir in os.supports_dir_fd
    and os.rename in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
    and os.unlink in os.supports_dir_fd
    and bool(getattr(os, "O_DIRECTORY", 0))
    and bool(getattr(os, "O_NOFOLLOW", 0))
)
SEVERITY_ORDER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
LIMITATIONS = [
    "The deterministic fixture detector is a runner/scoring smoke baseline, not a product efficacy claim.",
    "Synthetic results do not establish recall, precision, or severity accuracy on production repositories.",
    "Every detected fixture signal remains subject to human review and must not be published automatically.",
]


class EfficacyBenchmarkError(RuntimeError):
    """Raised when deterministic efficacy benchmark execution is unsafe or invalid."""


def available_suites(loaded: dict[str, Any]) -> list[str]:
    suites = {suite for entry in loaded["corpus"]["cases"] for suite in entry["suites"]}
    return sorted(suites)


def select_cases(
    loaded: dict[str, Any],
    *,
    suite: str | None = None,
    case_ids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if suite and case_ids:
        raise EfficacyBenchmarkError("--suite and --case cannot be combined")
    cases_by_id = {case["case_id"]: case for case in loaded["cases"]}
    entries_by_id = {entry["case_id"]: entry for entry in loaded["corpus"]["cases"]}
    if case_ids:
        if len(case_ids) != len(set(case_ids)):
            raise EfficacyBenchmarkError("--case values must be unique")
        unknown = sorted(set(case_ids) - set(cases_by_id))
        if unknown:
            raise EfficacyBenchmarkError(f"unknown efficacy benchmark case: {unknown[0]}")
        selected_ids = sorted(case_ids)
        selection = {"kind": "cases", "suite": None, "case_ids": selected_ids}
    else:
        selected_suite = suite or loaded["corpus"]["default_suite"]
        if selected_suite not in available_suites(loaded):
            raise EfficacyBenchmarkError(f"unknown efficacy benchmark suite: {selected_suite}")
        selected_ids = sorted(
            case_id for case_id, entry in entries_by_id.items() if selected_suite in entry["suites"]
        )
        selection = {"kind": "suite", "suite": selected_suite, "case_ids": selected_ids}
    if not selected_ids:
        raise EfficacyBenchmarkError("efficacy benchmark selection contains no cases")
    return [cases_by_id[case_id] for case_id in selected_ids], selection


def render_case_list(loaded: dict[str, Any], selected: list[dict[str, Any]]) -> str:
    entries = {entry["case_id"]: entry for entry in loaded["corpus"]["cases"]}
    lines = [
        f"Corpus: {loaded['corpus']['corpus_id']} {loaded['corpus']['corpus_version']}",
        "CASE ID\tCLASS\tCATEGORY\tSUITES",
    ]
    for case in selected:
        entry = entries[case["case_id"]]
        lines.append(
            f"{case['case_id']}\t{case['classification']}\t{case['category']}\t{','.join(entry['suites'])}"
        )
    return "\n".join(lines) + "\n"


def _yaml_scalars(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        if key and value.strip():
            values[key.strip()] = value.strip().strip("'\"")
    return values


def _json_fixture(texts: dict[str, str]) -> dict[str, Any]:
    for path, text in texts.items():
        if path.endswith(".json"):
            value = json.loads(text)
            if isinstance(value, dict):
                return value
    return {}


def analyze_fixture_case(case: dict[str, Any], texts: dict[str, str]) -> dict[str, Any]:
    predictions: list[dict[str, Any]] = []
    supported = False
    combined = "\n".join(texts[path] for path in sorted(texts))
    compact = "".join(combined.split())
    category = case["category"]

    if category == "python-web" and "defselect_invoice(" in compact:
        supported = True
        if 'row["tenant_id"]==actor_tenant' not in compact:
            predictions.append(
                {
                    "vulnerability_class": "missing-tenant-authorization",
                    "severity": "High",
                    "human_review_required": True,
                }
            )
    elif category == "python-web" and "defcandidate_path(" in compact:
        supported = True
        if "returnbase/user_name" in compact and ".resolve(" not in compact and ".relative_to(" not in compact:
            predictions.append(
                {
                    "vulnerability_class": "unsafe-path-normalization",
                    "severity": "Medium",
                    "human_review_required": True,
                }
            )
    elif category == "github-actions":
        supported = True
        values = _yaml_scalars(combined)
        if (
            values.get("permissions_model") == "repository_write"
            and values.get("content_source") == "untrusted_contributor_revision"
        ):
            predictions.append(
                {
                    "vulnerability_class": "privileged-workflow-untrusted-content",
                    "severity": "High",
                    "human_review_required": True,
                }
            )
    elif category == "ai-agent-mcp":
        supported = True
        value = _json_fixture(texts)
        if value.get("tool_allowlist_enforced") is False or value.get("tool_arguments_schema_enforced") is False:
            predictions.append(
                {
                    "vulnerability_class": "untrusted-tool-selection",
                    "severity": "High",
                    "human_review_required": True,
                }
            )
    elif category == "dependency-supply-chain":
        supported = True
        value = _json_fixture(texts)
        dependencies = value.get("dependencies") if isinstance(value.get("dependencies"), list) else []
        if any(
            isinstance(item, dict)
            and isinstance(item.get("advisory_id"), str)
            and item["advisory_id"].startswith("SYNTHETIC-")
            and isinstance(item.get("reachable_from"), list)
            and bool(item["reachable_from"])
            for item in dependencies
        ):
            predictions.append(
                {
                    "vulnerability_class": "reachable-vulnerable-dependency",
                    "severity": "Medium",
                    "human_review_required": True,
                }
            )

    predictions.sort(key=lambda item: (item["vulnerability_class"], item["severity"]))
    return {
        "predictions": predictions,
        "target_covered": bool(texts),
        "rule_supported": supported,
        "fixture_file_count": len(texts),
        "human_review_required": bool(predictions) or not supported,
    }


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def score_cases(cases: list[dict[str, Any]], analyses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    case_results: list[dict[str, Any]] = []
    totals = Counter()
    severity_eligible = 0
    severity_agreed = 0
    covered = 0
    human_review_required = 0
    fixture_files = 0
    supported_cases = 0

    for case in cases:
        case_id = case["case_id"]
        analysis = analyses.get(case_id)
        if not isinstance(analysis, dict):
            raise EfficacyBenchmarkError(f"missing deterministic analysis for case: {case_id}")
        predictions = analysis.get("predictions")
        if not isinstance(predictions, list):
            raise EfficacyBenchmarkError(f"invalid deterministic predictions for case: {case_id}")
        expected = case["ground_truth"]["positive_findings"]
        unmatched = set(range(len(predictions)))
        matched = 0
        case_severity_eligible = 0
        case_severity_agreed = 0
        for finding in expected:
            match_index = next(
                (
                    index
                    for index in sorted(unmatched)
                    if predictions[index].get("vulnerability_class") == finding["vulnerability_class"]
                ),
                None,
            )
            if match_index is None:
                totals["false_negatives"] += 1
                continue
            unmatched.remove(match_index)
            matched += 1
            totals["true_positives"] += 1
            case_severity_eligible += 1
            severity = predictions[match_index].get("severity")
            severity_range = finding["severity_range"]
            if (
                severity in SEVERITY_ORDER
                and SEVERITY_ORDER[severity_range["minimum"]]
                <= SEVERITY_ORDER[severity]
                <= SEVERITY_ORDER[severity_range["maximum"]]
            ):
                case_severity_agreed += 1
        totals["false_positives"] += len(unmatched)
        if case["classification"] == "negative_control" and not predictions:
            totals["true_negatives"] += 1

        case_fp = len(unmatched)
        case_fn = len(expected) - matched
        if case_fp and case_fn:
            outcome = "mixed"
        elif case_fp:
            outcome = "false_positive"
        elif case_fn:
            outcome = "false_negative"
        elif expected:
            outcome = "true_positive"
        else:
            outcome = "true_negative"

        target_covered = analysis.get("target_covered") is True
        review_required = analysis.get("human_review_required") is True
        rule_supported = analysis.get("rule_supported") is True
        covered += int(target_covered)
        human_review_required += int(review_required)
        supported_cases += int(rule_supported)
        fixture_files += int(analysis.get("fixture_file_count", 0))
        severity_eligible += case_severity_eligible
        severity_agreed += case_severity_agreed
        case_results.append(
            {
                "case_id": case_id,
                "case_version": case["case_version"],
                "classification": case["classification"],
                "category": case["category"],
                "outcome": outcome,
                "true_positives": matched,
                "false_positives": case_fp,
                "false_negatives": case_fn,
                "predicted_finding_count": len(predictions),
                "severity_agreement": {
                    "agreed": case_severity_agreed,
                    "eligible": case_severity_eligible,
                    "rate": _rate(case_severity_agreed, case_severity_eligible),
                },
                "target_covered": target_covered,
                "human_review_required": review_required,
                "rule_supported": rule_supported,
            }
        )

    tp = totals["true_positives"]
    fp = totals["false_positives"]
    fn = totals["false_negatives"]
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    f1 = None
    if precision is not None and recall is not None:
        f1 = 0.0 if precision + recall == 0 else round(2 * precision * recall / (precision + recall), 6)
    return {
        "counts": {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": totals["true_negatives"],
            "prediction_count": tp + fp,
        },
        "rates": {"precision": precision, "recall": recall, "f1": f1},
        "severity_agreement": {
            "agreed": severity_agreed,
            "eligible": severity_eligible,
            "rate": _rate(severity_agreed, severity_eligible),
        },
        "target_coverage": {
            "covered": covered,
            "selected": len(cases),
            "rate": _rate(covered, len(cases)),
        },
        "human_review_required_count": human_review_required,
        "supported_case_count": supported_cases,
        "fixture_file_count": fixture_files,
        "cases": case_results,
    }


def build_fixture_report(
    lab_root: Path,
    *,
    suite: str | None = None,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    try:
        loaded, fixture_texts = load_corpus_fixture_texts(lab_root)
    except EfficacyCorpusError as exc:
        raise EfficacyBenchmarkError(str(exc)) from exc
    cases, selection = select_cases(loaded, suite=suite, case_ids=case_ids)
    analyses = {case["case_id"]: analyze_fixture_case(case, fixture_texts[case["case_id"]]) for case in cases}
    scored = score_cases(cases, analyses)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "benchmark_id": "genai-repo-auditor-security-efficacy",
        "mode": "deterministic-fixture",
        "corpus": {
            "corpus_id": loaded["corpus"]["corpus_id"],
            "corpus_version": loaded["corpus"]["corpus_version"],
            "selection": selection,
        },
        "safety": {
            "local_synthetic_fixtures_only": True,
            "network_accessed": False,
            "github_accessed": False,
            "model_channel_used": False,
            "issue_publication_performed": False,
            "raw_fixture_content_included": False,
            "bounded_summary_only": True,
        },
        "execution": {
            "detector_id": DETECTOR_ID,
            "selected_case_count": len(cases),
            "supported_case_count": scored["supported_case_count"],
            "fixture_file_count": scored["fixture_file_count"],
        },
        "scores": {
            "counts": scored["counts"],
            "rates": scored["rates"],
            "severity_agreement": scored["severity_agreement"],
            "target_coverage": scored["target_coverage"],
            "human_review_required_count": scored["human_review_required_count"],
        },
        "cases": scored["cases"],
        "limitations": LIMITATIONS,
    }
    try:
        schema = load_schema_object(
            lab_root,
            "templates/reports/efficacy-benchmark.schema.json",
            label="efficacy benchmark schema",
        )
        validate_schema_object(report, schema, label="efficacy benchmark")
    except EfficacyCorpusError as exc:
        raise EfficacyBenchmarkError("efficacy benchmark report failed its closed schema contract") from exc
    return report


def render_markdown(report: dict[str, Any]) -> str:
    scores = report["scores"]
    counts = scores["counts"]
    rates = scores["rates"]
    selection = report["corpus"]["selection"]

    def display_rate(value: float | None) -> str:
        return "not applicable" if value is None else f"{value:.6f}"

    lines = [
        "# Security efficacy benchmark",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Corpus: `{report['corpus']['corpus_id']}`",
        f"- Corpus version: `{report['corpus']['corpus_version']}`",
        f"- Selection: `{selection['suite'] or ','.join(selection['case_ids'])}`",
        f"- Detector: `{report['execution']['detector_id']}`",
        "- Network/GitHub/model access: `false / false / false`",
        "",
        "## Aggregate scores",
        "",
        f"- True positives: {counts['true_positives']}",
        f"- False positives: {counts['false_positives']}",
        f"- False negatives: {counts['false_negatives']}",
        f"- True negatives: {counts['true_negatives']}",
        f"- Precision: {display_rate(rates['precision'])}",
        f"- Recall: {display_rate(rates['recall'])}",
        f"- F1: {display_rate(rates['f1'])}",
        f"- Severity agreement: {display_rate(scores['severity_agreement']['rate'])}",
        f"- Target coverage: {display_rate(scores['target_coverage']['rate'])}",
        f"- Human review required: {scores['human_review_required_count']}",
        "",
        "## Case outcomes",
        "",
        "| Case | Class | Outcome | TP | FP | FN | Severity | Covered | Human review |",
        "|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for case in report["cases"]:
        severity = case["severity_agreement"]
        lines.append(
            f"| `{case['case_id']}` | {case['classification']} | {case['outcome']} | "
            f"{case['true_positives']} | {case['false_positives']} | {case['false_negatives']} | "
            f"{severity['agreed']}/{severity['eligible']} | "
            f"{'yes' if case['target_covered'] else 'no'} | "
            f"{'yes' if case['human_review_required'] else 'no'} |"
        )
    lines.extend(["", "## Interpretation limits", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def _destination(path: Path) -> Path:
    destination = path.expanduser()
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    return Path(os.path.abspath(os.fspath(destination)))


def _open_output_parent(destination: Path) -> tuple[int, tuple[tuple[int, int, int], ...]]:
    if not DIR_FD_OUTPUT_SUPPORTED:
        raise EfficacyBenchmarkError(
            "safe efficacy benchmark report writes require dirfd support; use --list on this platform"
        )
    directory_fd: int | None = None
    try:
        directory_fd = os.open(
            destination.anchor,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(directory_fd)
        identities = [(opened.st_dev, opened.st_ino, opened.st_mode)]
        for component in destination.parts[1:-1]:
            try:
                next_fd = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
            except FileNotFoundError:
                os.mkdir(component, 0o700, dir_fd=directory_fd)
                next_fd = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
            opened = os.fstat(next_fd)
            identities.append((opened.st_dev, opened.st_ino, opened.st_mode))
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd, tuple(identities)
    except OSError as exc:
        if directory_fd is not None:
            os.close(directory_fd)
        raise EfficacyBenchmarkError(
            "efficacy benchmark output parent must be a symlink-free directory"
        ) from exc


@dataclass
class _StagedOutput:
    destination: Path
    temporary_name: str
    parent_fd: int
    parent_identity: tuple[tuple[int, int, int], ...]


def _portable_components(destination: Path) -> list[Path]:
    current = Path(destination.anchor)
    components = [current]
    for component in destination.parts[1:-1]:
        current = current / component
        components.append(current)
    return components


def _verify_parent_identity(staged: _StagedOutput) -> None:
    try:
        metadata = os.fstat(staged.parent_fd)
        descriptor_identity = (metadata.st_dev, metadata.st_ino, metadata.st_mode)
        path_identity = tuple(
            (item.st_dev, item.st_ino, item.st_mode)
            for item in map(os.lstat, _portable_components(staged.destination))
        )
        if descriptor_identity != staged.parent_identity[-1] or path_identity != staged.parent_identity:
            raise EfficacyBenchmarkError("efficacy benchmark output parent changed during execution")
    except OSError as exc:
        raise EfficacyBenchmarkError("efficacy benchmark output parent changed during execution") from exc


def _leaf_metadata(staged: _StagedOutput, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=staged.parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _rename_leaf(staged: _StagedOutput, source: str, destination: str) -> None:
    os.rename(
        source,
        destination,
        src_dir_fd=staged.parent_fd,
        dst_dir_fd=staged.parent_fd,
    )


def _unlink_leaf(staged: _StagedOutput, name: str) -> None:
    os.unlink(name, dir_fd=staged.parent_fd)


def _close_staged(staged: _StagedOutput) -> None:
    if staged.parent_fd >= 0:
        os.close(staged.parent_fd)
        staged.parent_fd = -1


def _stage_write(path: Path, content: str) -> _StagedOutput:
    destination = _destination(path)
    payload = content.encode("utf-8")
    if len(payload) > MAX_REPORT_BYTES:
        raise EfficacyBenchmarkError("efficacy benchmark output exceeds the size limit")
    parent_fd, parent_identity = _open_output_parent(destination)
    temporary_name = f".{destination.name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        fd = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise EfficacyBenchmarkError("efficacy benchmark temporary output must be a regular file")
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise EfficacyBenchmarkError("efficacy benchmark output write made no progress")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = None
        staged = _StagedOutput(destination, temporary_name, parent_fd, parent_identity)
        _verify_parent_identity(staged)
        return staged
    except BaseException:
        try:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary_name, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        raise
    finally:
        if fd is not None:
            os.close(fd)


def _commit_staged_outputs(staged_outputs: list[_StagedOutput]) -> None:
    backups: list[tuple[_StagedOutput, str | None]] = []
    installed: list[_StagedOutput] = []
    try:
        for staged in staged_outputs:
            _verify_parent_identity(staged)
            metadata = _leaf_metadata(staged, staged.destination.name)
            if metadata is not None and not stat.S_ISREG(metadata.st_mode):
                raise EfficacyBenchmarkError("efficacy benchmark output must be a regular non-symlink file")
            backup = None
            if metadata is not None:
                backup = f".{staged.destination.name}.{uuid.uuid4().hex}.backup"
                _rename_leaf(staged, staged.destination.name, backup)
            backups.append((staged, backup))
        for staged in staged_outputs:
            _rename_leaf(staged, staged.temporary_name, staged.destination.name)
            installed.append(staged)
        for staged in staged_outputs:
            _verify_parent_identity(staged)
    except BaseException as exc:
        rollback_errors: list[OSError] = []
        for staged in reversed(installed):
            try:
                _unlink_leaf(staged, staged.destination.name)
            except FileNotFoundError:
                # A concurrent removal already achieved this rollback step.
                pass
            except OSError as rollback_exc:
                rollback_errors.append(rollback_exc)
        for staged, backup in reversed(backups):
            if backup is None:
                continue
            try:
                _rename_leaf(staged, backup, staged.destination.name)
            except OSError as rollback_exc:
                rollback_errors.append(rollback_exc)
        if rollback_errors:
            raise EfficacyBenchmarkError(
                "efficacy benchmark output commit failed and rollback was incomplete"
            ) from exc
        raise
    else:
        for staged, backup in backups:
            if backup is not None:
                with contextlib.suppress(FileNotFoundError):
                    _unlink_leaf(staged, backup)


def write_report(report: dict[str, Any], json_path: Path, markdown_path: Path) -> tuple[Path, Path]:
    json_destination = _destination(json_path)
    markdown_destination = _destination(markdown_path)
    if json_destination == markdown_destination:
        raise EfficacyBenchmarkError("JSON and Markdown outputs must use different paths")
    staged_outputs: list[_StagedOutput] = []
    try:
        staged_outputs.append(
            _stage_write(
                json_destination,
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
        )
        staged_outputs.append(_stage_write(markdown_destination, render_markdown(report)))
        _commit_staged_outputs(staged_outputs)
    finally:
        for staged in staged_outputs:
            try:
                with contextlib.suppress(FileNotFoundError):
                    _unlink_leaf(staged, staged.temporary_name)
            finally:
                _close_staged(staged)
    return json_destination, markdown_destination
