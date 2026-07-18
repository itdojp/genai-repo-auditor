from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from pathlib import Path
from typing import Any

from gralib import utc_now, write_run_artifact_json, write_run_artifact_text
from provider_failures import (
    PROVIDER_ERROR_CLASSES,
    ProviderFailureError,
    validate_provider_error,
    validate_provider_failure_history,
)
from report_safety import iter_secret_findings
from run_events import reports_dir


WORKFLOW_EXECUTION_SCHEMA_VERSION = "1"
STAGE_STATUSES = [
    "pending",
    "running",
    "succeeded",
    "failed",
    "blocked_dependency",
    "external_prerequisite",
    "skipped_by_scope",
    "out_of_range",
]
WORKFLOW_STATUSES = {"running", "paused", "blocked", "succeeded"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class WorkflowExecutionReportError(RuntimeError):
    pass


def _safe_id(value: Any, default: str = "not-recorded") -> str:
    text = str(value or "")
    return text if SAFE_ID_RE.fullmatch(text) else default


def summarize_workflow_execution(value: Any) -> dict[str, Any]:
    default = {
        "artifact_present": False,
        "absence_reason": "workflow_execution_not_recorded",
        "status": "not-recorded",
        "profile": "not-recorded",
        "stage_count": 0,
        "by_status": {status: 0 for status in STAGE_STATUSES},
        "total_duration_ms": 0,
        "maximum_duration_ms": 0,
        "failed_count": 0,
        "failed_stages": [],
        "skipped_by_scope_count": 0,
        "scoped_skip_stages": [],
        "blocked_dependency_count": 0,
        "blocked_dependency_stages": [],
        "absent_stage_count": 0,
        "absence_reasons": {"workflow_execution_not_recorded": 1},
        "resume_available": False,
        "resume_stage": None,
        "provider_failure_count": 0,
        "retryable_provider_failure_count": 0,
        "resume_recommended_count": 0,
        "active_provider_failure_count": 0,
        "recovered_provider_failure_count": 0,
        "provider_failures_by_class": {},
        "provider_failure_stages": [],
        "recovered_provider_failure_stages": [],
    }
    if not isinstance(value, dict) or not value:
        return default
    stages = [stage for stage in value.get("stages") or [] if isinstance(stage, dict)]
    statuses = Counter(
        str(stage.get("status")) if stage.get("status") in STAGE_STATUSES else "pending"
        for stage in stages
    )
    safe_stage_ids = {
        index: _safe_id(stage.get("id"), f"stage-{index + 1}")
        for index, stage in enumerate(stages)
    }
    durations = [
        int(stage.get("duration_ms"))
        for stage in stages
        if isinstance(stage.get("duration_ms"), int)
        and not isinstance(stage.get("duration_ms"), bool)
        and stage.get("duration_ms") >= 0
    ]
    absence_reasons = Counter(
        _safe_id(stage.get("absence_reason"), "unknown")
        for stage in stages
        if stage.get("absence_reason") is not None
    )
    status = str(value.get("status") or "")
    resume = value.get("resume") if isinstance(value.get("resume"), dict) else {}
    resume_stage = _safe_id(resume.get("stage"), "") or None
    provider_histories: list[tuple[str, dict[str, Any], bool]] = []
    for index, stage in enumerate(stages):
        history = stage.get("provider_failure_history")
        try:
            validate_provider_failure_history(history)
        except ProviderFailureError:
            continue
        provider_histories.append((
            safe_stage_ids[index],
            history,
            isinstance(stage.get("provider_error"), dict),
        ))
    provider_classes: Counter[str] = Counter()
    for _stage_id, history, _active in provider_histories:
        provider_classes.update(history["by_class"])
    return {
        "artifact_present": True,
        "absence_reason": None,
        "status": status if status in WORKFLOW_STATUSES else "not-recorded",
        "profile": _safe_id(value.get("profile")),
        "stage_count": len(stages),
        "by_status": {stage_status: int(statuses.get(stage_status, 0)) for stage_status in STAGE_STATUSES},
        "total_duration_ms": sum(durations),
        "maximum_duration_ms": max(durations, default=0),
        "failed_count": int(statuses.get("failed", 0)),
        "failed_stages": [safe_stage_ids[index] for index, stage in enumerate(stages) if stage.get("status") == "failed"],
        "skipped_by_scope_count": int(statuses.get("skipped_by_scope", 0)),
        "scoped_skip_stages": [safe_stage_ids[index] for index, stage in enumerate(stages) if stage.get("status") == "skipped_by_scope"],
        "blocked_dependency_count": int(statuses.get("blocked_dependency", 0)),
        "blocked_dependency_stages": [safe_stage_ids[index] for index, stage in enumerate(stages) if stage.get("status") == "blocked_dependency"],
        "absent_stage_count": sum(absence_reasons.values()),
        "absence_reasons": dict(sorted(absence_reasons.items())),
        "resume_available": bool(resume.get("available")) and resume_stage is not None,
        "resume_stage": resume_stage,
        "provider_failure_count": sum(history["count"] for _stage_id, history, _active in provider_histories),
        "retryable_provider_failure_count": sum(
            history["retryable_count"] for _stage_id, history, _active in provider_histories
        ),
        "resume_recommended_count": sum(
            history["resume_recommended_count"] for _stage_id, history, _active in provider_histories
        ),
        "active_provider_failure_count": sum(1 for _stage_id, _history, active in provider_histories if active),
        "recovered_provider_failure_count": sum(
            1 for _stage_id, history, _active in provider_histories if history["recovered"]
        ),
        "provider_failures_by_class": {
            error_class: int(provider_classes[error_class])
            for error_class in PROVIDER_ERROR_CLASSES
            if provider_classes[error_class]
        },
        "provider_failure_stages": [stage_id for stage_id, _history, _active in provider_histories],
        "recovered_provider_failure_stages": [
            stage_id for stage_id, history, _active in provider_histories if history["recovered"]
        ],
    }


def _duration_ms(started_at: Any, ended_at: Any) -> int:
    if not isinstance(started_at, str) or not isinstance(ended_at, str):
        return 0
    try:
        start = dt.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = dt.datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    except (OverflowError, TypeError, ValueError):
        return 0
    try:
        return max(0, int((end - start).total_seconds() * 1000))
    except (OverflowError, TypeError, ValueError):
        return 0


def _absence_reason(
    checkpoint: dict[str, Any],
    record: dict[str, Any],
    blocked_by: list[str],
) -> str | None:
    status = str(record.get("status") or "pending")
    if record.get("error_category") == "interrupted":
        return "interrupted"
    if status == "skipped_by_scope":
        return "operator_scoped_skip"
    if status == "external_prerequisite":
        return "external_prerequisite"
    if status == "out_of_range":
        return "outside_selected_range"
    if status == "blocked_dependency" or blocked_by:
        return "blocked_by_dependency"
    if status != "pending":
        return None
    if checkpoint.get("requested_until") is not None:
        return "range_continuation"
    if checkpoint.get("status") == "paused":
        return "workflow_paused"
    if checkpoint.get("status") == "blocked":
        return "workflow_blocked"
    return "not_started"


def build_workflow_execution(
    checkpoint: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    plan_stages = {
        str(stage.get("id") or ""): stage
        for stage in plan.get("stages") or []
        if isinstance(stage, dict)
    }
    records = {
        str(record.get("id") or ""): record
        for record in checkpoint.get("stages") or []
        if isinstance(record, dict)
    }
    stages: list[dict[str, Any]] = []
    for stage_id, stage in plan_stages.items():
        record = records.get(stage_id, {})
        provider_error = record.get("provider_error")
        provider_history = record.get("provider_failure_history")
        try:
            validate_provider_error(provider_error, allow_none=True)
            validate_provider_failure_history(provider_history, allow_none=True)
        except ProviderFailureError as exc:
            raise WorkflowExecutionReportError("workflow stage provider failure metadata is invalid") from exc
        error_category = record.get("error_category") if isinstance(record.get("error_category"), str) else None
        if (error_category == "provider_error") != (provider_error is not None):
            raise WorkflowExecutionReportError("workflow stage provider failure state is inconsistent")
        if provider_error is not None and record.get("status") != "failed":
            raise WorkflowExecutionReportError("workflow stage provider failure requires failed status")
        if provider_error is not None and (
            provider_history is None
            or provider_history["last_error"] != provider_error
            or provider_history["recovered"]
        ):
            raise WorkflowExecutionReportError("workflow stage provider failure history is inconsistent")
        if provider_history is not None:
            if provider_history["count"] > int(record.get("attempt") or 0):
                raise WorkflowExecutionReportError("workflow stage provider failure count exceeds attempts")
            if provider_history["recovered"] != (record.get("status") == "succeeded"):
                raise WorkflowExecutionReportError("workflow stage provider recovery state is inconsistent")
        dependencies = [str(value) for value in stage.get("depends_on") or [] if isinstance(value, str)]
        blocked_by = [
            dependency
            for dependency in dependencies
            if records.get(dependency, {}).get("status") not in {
                "succeeded",
                "external_prerequisite",
                "skipped_by_scope",
            }
        ]
        output_refs = [
            str(item.get("path"))
            for item in record.get("output_artifacts") or []
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        ]
        stage_report = {
            "id": stage_id,
            "status": str(record.get("status") or "pending"),
            "depends_on": dependencies,
            "attempt": int(record.get("attempt") or 0),
            "started_at": record.get("started_at") if isinstance(record.get("started_at"), str) else None,
            "ended_at": record.get("ended_at") if isinstance(record.get("ended_at"), str) else None,
            "duration_ms": _duration_ms(record.get("started_at"), record.get("ended_at")),
            "exit_code": record.get("exit_code") if isinstance(record.get("exit_code"), int) else None,
            "error_category": error_category,
            "provider_error": provider_error,
            "provider_failure_history": provider_history,
            "absence_reason": None,
            "blocked_by": blocked_by,
            "output_artifact_refs": output_refs,
        }
        stage_report["absence_reason"] = _absence_reason(checkpoint, record, blocked_by)
        stages.append(stage_report)

    statuses = Counter(stage["status"] for stage in stages)
    absence_reasons = Counter(
        stage["absence_reason"] for stage in stages if stage["absence_reason"] is not None
    )
    durations = [stage["duration_ms"] for stage in stages]
    provider_history_stages = [stage for stage in stages if stage["provider_failure_history"] is not None]
    active_provider_stages = [stage for stage in provider_history_stages if stage["provider_error"] is not None]
    recovered_provider_stages = [
        stage for stage in provider_history_stages if stage["provider_failure_history"]["recovered"]
    ]
    provider_classes: Counter[str] = Counter()
    for stage in provider_history_stages:
        provider_classes.update(stage["provider_failure_history"]["by_class"])
    report = {
        "schema_version": WORKFLOW_EXECUTION_SCHEMA_VERSION,
        "run_id": str(checkpoint.get("run_id") or ""),
        "repo": str(checkpoint.get("repo") or ""),
        "generated_at": utc_now(),
        "source": "gra-run-execution",
        "profile": str(checkpoint.get("profile") or ""),
        "profile_version": str(checkpoint.get("profile_version") or ""),
        "status": str(checkpoint.get("status") or "running"),
        "requested_range": {
            "from": checkpoint.get("requested_from"),
            "until": checkpoint.get("requested_until"),
        },
        "requested_skips": [
            str(value) for value in checkpoint.get("requested_skips") or [] if isinstance(value, str)
        ],
        "resume": {
            "available": checkpoint.get("resume_stage") is not None,
            "stage": checkpoint.get("resume_stage"),
        },
        "safety": {
            "local_artifacts_only": True,
            "raw_prompts_copied": False,
            "raw_findings_copied": False,
            "raw_evidence_copied": False,
            "credentials_copied": False,
            "private_reasoning_copied": False,
            "issue_publication_included": False,
        },
        "summary": {
            "stage_count": len(stages),
            "by_status": {status: int(statuses.get(status, 0)) for status in STAGE_STATUSES},
            "total_duration_ms": sum(durations),
            "maximum_duration_ms": max(durations, default=0),
            "failed_count": int(statuses.get("failed", 0)),
            "skipped_by_scope_count": int(statuses.get("skipped_by_scope", 0)),
            "blocked_dependency_count": int(statuses.get("blocked_dependency", 0)),
            "absent_stage_count": sum(1 for stage in stages if stage["absence_reason"] is not None),
            "absence_reasons": dict(sorted(absence_reasons.items())),
            "provider_failure_count": sum(
                stage["provider_failure_history"]["count"] for stage in provider_history_stages
            ),
            "retryable_provider_failure_count": sum(
                stage["provider_failure_history"]["retryable_count"] for stage in provider_history_stages
            ),
            "resume_recommended_count": sum(
                stage["provider_failure_history"]["resume_recommended_count"]
                for stage in provider_history_stages
            ),
            "active_provider_failure_count": len(active_provider_stages),
            "recovered_provider_failure_count": len(recovered_provider_stages),
            "provider_failures_by_class": {
                error_class: int(provider_classes[error_class])
                for error_class in PROVIDER_ERROR_CLASSES
                if provider_classes[error_class]
            },
        },
        "stages": stages,
    }
    if list(iter_secret_findings(report, field_path="workflow_execution")):
        raise WorkflowExecutionReportError("workflow execution report contains secret-like values")
    return report


def render_workflow_execution_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Workflow Execution",
        "",
        "Local-only bounded workflow status. It excludes prompts, findings, evidence, credentials, private reasoning, and Issue publication.",
        "",
        f"- Profile: `{report['profile']}` `{report['profile_version']}`",
        f"- Status: `{report['status']}`",
        f"- Resume stage: `{report['resume']['stage'] or '-'}`",
        f"- Total stage duration: {summary['total_duration_ms']} ms",
        f"- Provider failures: {summary['provider_failure_count']}",
        f"- Active provider failures: {summary['active_provider_failure_count']}",
        f"- Recovered provider-failure stages: {summary['recovered_provider_failure_count']}",
        f"- Retryable provider failures: {summary['retryable_provider_failure_count']}",
        "",
        "| Stage | Status | Duration | Attempts | Last provider class | Provider recovery | Resume guidance | Absence reason | Blocked by |",
        "|---|---|---:|---:|---|---|---|---|---|",
    ]
    for stage in report["stages"]:
        lines.append(
            f"| `{stage['id']}` | {stage['status']} | {stage['duration_ms']} ms | "
            f"{stage['attempt']} | {((stage['provider_failure_history'] or {}).get('last_error') or {}).get('class', '-')} | "
            f"{'recovered' if (stage['provider_failure_history'] or {}).get('recovered') else '-'} | "
            f"{'recommended' if (stage['provider_error'] or {}).get('resume_recommended') else '-'} | "
            f"{stage['absence_reason'] or '-'} | "
            f"{', '.join(stage['blocked_by']) or '-'} |"
        )
    lines.extend([
        "",
        "Issue publication is not part of this workflow execution.",
        "",
    ])
    return "\n".join(lines)


def write_workflow_execution(
    run_dir: Path,
    checkpoint: dict[str, Any],
    plan: dict[str, Any],
) -> tuple[Path, Path, dict[str, Any]]:
    report = build_workflow_execution(checkpoint, plan)
    reports = reports_dir(run_dir)
    json_path = reports / "workflow-execution.json"
    markdown_path = reports / "WORKFLOW_EXECUTION.md"
    write_run_artifact_json(run_dir, json_path, report)
    write_run_artifact_text(run_dir, markdown_path, render_workflow_execution_markdown(report))
    return json_path, markdown_path, report
