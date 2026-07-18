from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Iterable

from gralib import utc_now, write_run_artifact_json, write_run_artifact_text
from publication.policy import finding_selection_outcome
from report_freshness import (
    FreshnessError,
    load_bounded_json_artifact,
    load_bounded_text_artifact,
)
from run_events import reports_dir

SUMMARY_JSON_NAME = "issue-dry-run-summary.json"
SUMMARY_MARKDOWN_NAME = "ISSUE_DRY_RUN_SUMMARY.md"
MAX_COUNT = 1_000_000
COUNT_KEYS = (
    "total_candidates",
    "selected",
    "filtered_by_severity_or_status",
    "issue_recommendation_suppressed",
    "novelty_suppressed",
    "duplicate_suppressed",
    "advanced_validation_blocked",
    "public_visibility_blocked",
    "would_create",
    "warnings",
    "issues_created",
)
SELECTION_SOURCES = {"current-findings", "verified-publication-plan"}
VISIBILITIES = {"PRIVATE", "PUBLIC", "INTERNAL", "UNKNOWN"}
VISIBILITY_SOURCES = {"run-artifact", "verified-publication-plan", "not-available"}


class IssueDryRunSummaryError(ValueError):
    pass


def summary_paths(run_dir: Path) -> tuple[Path, Path]:
    root = reports_dir(run_dir)
    return root / SUMMARY_JSON_NAME, root / SUMMARY_MARKDOWN_NAME


def selection_counts(
    *,
    repo: str,
    findings: Iterable[dict[str, Any]],
    min_severity: str,
    statuses: Iterable[str],
    novelty_entries: dict[str, dict[str, Any]],
) -> dict[str, int]:
    counts = {
        "total_candidates": 0,
        "selected": 0,
        "filtered_by_severity_or_status": 0,
        "issue_recommendation_suppressed": 0,
        "novelty_suppressed": 0,
    }
    for finding in findings:
        counts["total_candidates"] += 1
        selected, _reason, reason_code = finding_selection_outcome(
            finding,
            min_severity,
            statuses,
            repo=repo,
            novelty_entries=novelty_entries,
        )
        key = "selected" if selected else reason_code
        counts[key] += 1
    return counts


def warning_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(
            len(item) if key == "warnings" and isinstance(item, list) else warning_count(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return sum(warning_count(item) for item in value)
    return 0


def build_summary(
    *,
    repo: str,
    run_id: str,
    commit: str,
    selection_source: str,
    visibility: str,
    visibility_source: str,
    base_counts: dict[str, int],
    duplicate_suppressed: int,
    advanced_validation_blocked: int,
    public_visibility_blocked: int,
    would_create: int,
    warnings: int,
) -> dict[str, Any]:
    counts = {
        **base_counts,
        "duplicate_suppressed": duplicate_suppressed,
        "advanced_validation_blocked": advanced_validation_blocked,
        "public_visibility_blocked": public_visibility_blocked,
        "would_create": would_create,
        "warnings": warnings,
        "issues_created": 0,
    }
    summary = {
        "schema_version": "1",
        "generated_at": utc_now(),
        "source": "local-issue-dry-run",
        "mode": "dry-run",
        "repo": repo,
        "run_id": run_id,
        "commit": commit,
        "selection_source": selection_source,
        "visibility": visibility if visibility in VISIBILITIES else "UNKNOWN",
        "visibility_source": visibility_source,
        "github_duplicate_search_performed": False,
        "github_visibility_lookup_performed": False,
        "counts": counts,
        "safety": {
            "local_artifacts_only": True,
            "github_mutation_performed": False,
            "publication_plan_written": False,
            "finding_content_copied": False,
            "raw_github_response_copied": False,
        },
    }
    errors = validate_summary(summary)
    if errors:
        raise IssueDryRunSummaryError("; ".join(errors))
    return summary


def validate_summary(
    data: Any,
    *,
    expected_run_id: str | None = None,
    expected_repo: str | None = None,
) -> list[str]:
    errors: list[str] = []
    expected_top = {
        "schema_version",
        "generated_at",
        "source",
        "mode",
        "repo",
        "run_id",
        "commit",
        "selection_source",
        "visibility",
        "visibility_source",
        "github_duplicate_search_performed",
        "github_visibility_lookup_performed",
        "counts",
        "safety",
    }
    if not isinstance(data, dict):
        return ["summary must be an object"]
    if set(data) != expected_top:
        errors.append("summary must contain exactly the supported fields")
    if data.get("schema_version") != "1":
        errors.append("schema_version must be 1")
    if data.get("source") != "local-issue-dry-run" or data.get("mode") != "dry-run":
        errors.append("source and mode must identify a local dry-run preview")
    if data.get("selection_source") not in SELECTION_SOURCES:
        errors.append("selection_source is unsupported")
    if data.get("visibility") not in VISIBILITIES:
        errors.append("visibility is unsupported")
    if data.get("visibility_source") not in VISIBILITY_SOURCES:
        errors.append("visibility_source is unsupported")
    for key, minimum, maximum in [
        ("repo", 1, 240),
        ("run_id", 1, 128),
        ("commit", 0, 128),
        ("generated_at", 1, 64),
    ]:
        value = data.get(key)
        if not isinstance(value, str) or not minimum <= len(value) <= maximum:
            errors.append(f"{key} must be a bounded string")
    generated_at = data.get("generated_at")
    if isinstance(generated_at, str):
        try:
            parsed_generated_at = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("generated_at must be an ISO-8601 timestamp")
        else:
            if parsed_generated_at.tzinfo is None:
                errors.append("generated_at must include a timezone")
    if data.get("github_duplicate_search_performed") is not False:
        errors.append("github_duplicate_search_performed must be false")
    if data.get("github_visibility_lookup_performed") is not False:
        errors.append("github_visibility_lookup_performed must be false")
    if expected_run_id is not None and data.get("run_id") != expected_run_id:
        errors.append("run_id does not match run context")
    if expected_repo is not None and data.get("repo") != expected_repo:
        errors.append("repo does not match run context")

    counts = data.get("counts")
    if not isinstance(counts, dict) or set(counts) != set(COUNT_KEYS):
        errors.append("counts must contain exactly the supported counters")
    else:
        for key in COUNT_KEYS:
            value = counts.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_COUNT:
                errors.append(f"counts.{key} must be a bounded non-negative integer")
        if not errors or all(not error.startswith("counts.") for error in errors):
            if counts["total_candidates"] != (
                counts["selected"]
                + counts["filtered_by_severity_or_status"]
                + counts["issue_recommendation_suppressed"]
                + counts["novelty_suppressed"]
            ):
                errors.append("selection counters do not partition total_candidates")
            if counts["selected"] != (
                counts["duplicate_suppressed"]
                + counts["advanced_validation_blocked"]
                + counts["public_visibility_blocked"]
                + counts["would_create"]
            ):
                errors.append("publication counters do not partition selected")
            if counts["issues_created"] != 0:
                errors.append("issues_created must be zero in dry-run mode")

    safety = data.get("safety")
    expected_safety = {
        "local_artifacts_only": True,
        "github_mutation_performed": False,
        "publication_plan_written": False,
        "finding_content_copied": False,
        "raw_github_response_copied": False,
    }
    if safety != expected_safety:
        errors.append("safety flags must preserve local preview-only behavior")
    return errors


def render_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    lines = [
        "# GitHub Issue dry-run summary",
        "",
        "> Sanitized local aggregate. It contains no finding title, body, path, fingerprint, labels, or GitHub response.",
        "",
        f"- Repository: `{summary['repo']}`",
        f"- Run ID: `{summary['run_id']}`",
        f"- Selection source: `{summary['selection_source']}`",
        f"- Declared visibility: `{summary['visibility']}` (`{summary['visibility_source']}`)",
        "- GitHub lookup or mutation: `false`",
        "- Publication plan written: `false`",
        "",
        "| Counter | Value |",
        "|---|---:|",
    ]
    lines.extend(f"| `{key}` | {counts[key]} |" for key in COUNT_KEYS)
    return "\n".join(lines) + "\n"


def write_summary(run_dir: Path, summary: dict[str, Any]) -> tuple[Path, Path]:
    errors = validate_summary(summary)
    if errors:
        raise IssueDryRunSummaryError("; ".join(errors))
    json_path, markdown_path = summary_paths(run_dir)
    write_run_artifact_json(run_dir, json_path, summary)
    write_run_artifact_text(run_dir, markdown_path, render_markdown(summary))
    return json_path, markdown_path


def read_summary(run_dir: Path) -> dict[str, Any] | None:
    json_path, markdown_path = summary_paths(run_dir)
    try:
        json_path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise IssueDryRunSummaryError(f"invalid bounded dry-run summary: {exc}") from exc
    if json_path.is_symlink():
        raise IssueDryRunSummaryError("invalid bounded dry-run summary: artifact path must not be a symlink")
    ref = json_path.relative_to(run_dir)
    try:
        data = load_bounded_json_artifact(run_dir, ref, max_bytes=64 * 1024)
    except (OSError, ValueError, FreshnessError) as exc:
        raise IssueDryRunSummaryError(f"invalid bounded dry-run summary: {exc}") from exc
    context_run_id = run_dir.name
    context_repo: str | None = None
    context_path = run_dir / "context.json"
    if context_path.is_file() and not context_path.is_symlink():
        import json

        try:
            context = json.loads(context_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IssueDryRunSummaryError(f"could not read run context: {exc}") from exc
        if isinstance(context, dict):
            context_run_id = str(context.get("run_id") or context_run_id)
            context_repo = str(context.get("repo")) if context.get("repo") is not None else None
    errors = validate_summary(data, expected_run_id=context_run_id, expected_repo=context_repo)
    if errors:
        raise IssueDryRunSummaryError("; ".join(errors))
    try:
        markdown = load_bounded_text_artifact(
            run_dir,
            markdown_path.relative_to(run_dir),
            max_bytes=64 * 1024,
        )
    except (OSError, ValueError, FreshnessError) as exc:
        raise IssueDryRunSummaryError(f"invalid bounded dry-run Markdown summary: {exc}") from exc
    if markdown != render_markdown(data):
        raise IssueDryRunSummaryError("dry-run JSON and Markdown summaries do not match")
    return data
