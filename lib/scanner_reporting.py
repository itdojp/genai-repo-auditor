from __future__ import annotations

import json
import os
import re
import stat
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from report_safety import iter_secret_findings
from run_events import load_context, reports_dir, utc_now


SCHEMA_VERSION = "1"
MAX_SCANNER_RUNS = 1_000
SCANNER_RUN_STATUSES = ("succeeded", "failed")
SCANNER_RUNS_JSON = "scanner-runs.json"
SCANNER_RUNS_MARKDOWN = "SCANNER_RUNS.md"
_SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:/@+=-]{0,127}$")
_RECORD_KEYS = {
    "id",
    "adapter_id",
    "tool_version",
    "image_digest",
    "status",
    "scanner_status",
    "started_at",
    "ended_at",
    "duration_ms",
    "scanner_exit_code",
    "result_count",
    "normalized_leads_count",
    "redaction_count",
    "sandbox_profile",
    "runtime",
    "network_accessed",
    "result_classification",
    "finding_status",
    "normalized_result_ref",
    "scanner_index_ref",
}


class ScannerReportError(RuntimeError):
    """Raised when a public-safe scanner report cannot be written."""


def scanner_report_paths(run_dir: Path) -> tuple[Path, Path]:
    reports = reports_dir(run_dir)
    return reports / SCANNER_RUNS_JSON, reports / SCANNER_RUNS_MARKDOWN


def _load_existing(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ScannerReportError("scanner-runs.json must be a regular non-symlink file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScannerReportError("scanner-runs.json must contain valid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
        raise ScannerReportError("scanner-runs.json must contain a runs array")
    if len(payload["runs"]) >= MAX_SCANNER_RUNS:
        raise ScannerReportError(f"scanner-runs.json is limited to {MAX_SCANNER_RUNS} records")
    validate_scanner_runs_report(payload)
    return payload


def preflight_scanner_reports(run_dir: Path) -> tuple[Path, Path]:
    json_path, markdown_path = scanner_report_paths(run_dir)
    for path in (json_path, markdown_path):
        current = run_dir
        try:
            relative = path.relative_to(run_dir)
        except ValueError as exc:
            raise ScannerReportError("scanner report paths must stay under the run directory") from exc
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ScannerReportError("scanner report paths must not contain symlink components")
        if path.exists() and not path.is_file():
            raise ScannerReportError("scanner report path must be a regular file")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    _load_existing(json_path)
    return json_path, markdown_path


def _safe_text(value: Any, *, field: str, fallback: str = "unknown") -> str:
    text = str(value or fallback)
    if not _SAFE_VALUE_RE.fullmatch(text):
        raise ScannerReportError(f"{field} contains unsupported characters")
    return text


def _safe_artifact_ref(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ScannerReportError(f"{field} must be a non-empty run-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ScannerReportError(f"{field} must be a contained run-relative path")
    if path.suffix.lower() != ".json":
        raise ScannerReportError(f"{field} must reference a JSON artifact")
    parts = path.parts
    if field == "normalized_result_ref" and (
        len(parts) < 3 or tuple(parts[-3:-1]) != ("scanner-results", "normalized")
    ):
        raise ScannerReportError("normalized_result_ref must reference a normalized scanner artifact")
    if field == "scanner_index_ref" and (
        len(parts) < 2 or tuple(parts[-2:]) != ("scanner-results", "scanner-index.json")
    ):
        raise ScannerReportError("scanner_index_ref must reference scanner-results/scanner-index.json")
    return value


def _parse_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ScannerReportError(f"{field} must be a timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScannerReportError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ScannerReportError(f"{field} must include a timezone")
    return parsed


def validate_scanner_run_record(record: dict[str, Any]) -> None:
    if not isinstance(record, dict) or set(record) != _RECORD_KEYS:
        raise ScannerReportError("scanner run record fields do not match the public-safe contract")
    record_id = str(record.get("id") or "")
    if not re.fullmatch(r"scan-[0-9a-f-]{36}", record_id):
        raise ScannerReportError("scanner run id is invalid")
    try:
        if str(uuid.UUID(record_id.removeprefix("scan-"))) != record_id.removeprefix("scan-"):
            raise ValueError
    except ValueError as exc:
        raise ScannerReportError("scanner run id is invalid") from exc
    for field in ("adapter_id", "tool_version", "scanner_status", "sandbox_profile", "runtime", "result_classification"):
        _safe_text(record.get(field), field=field)
    if record.get("sandbox_profile") not in {"container", "gvisor"}:
        raise ScannerReportError("scanner run sandbox_profile is invalid")
    if record.get("runtime") not in {"docker", "podman", "unknown"}:
        raise ScannerReportError("scanner run runtime is invalid")
    if record.get("result_classification") not in {"scanner-leads", "posture-evidence", "sbom-data"}:
        raise ScannerReportError("scanner run result_classification is invalid")
    if record.get("status") not in SCANNER_RUN_STATUSES:
        raise ScannerReportError("scanner run status is invalid")
    if record.get("finding_status") != "review-only" or record.get("network_accessed") is not False:
        raise ScannerReportError("scanner run records must remain offline and review-only")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", str(record.get("image_digest") or "")):
        raise ScannerReportError("scanner image digest is invalid")
    for field in ("duration_ms", "result_count", "normalized_leads_count", "redaction_count"):
        value = record.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ScannerReportError(f"{field} must be a non-negative integer")
    scanner_exit_code = record.get("scanner_exit_code")
    if scanner_exit_code is not None and (not isinstance(scanner_exit_code, int) or isinstance(scanner_exit_code, bool)):
        raise ScannerReportError("scanner_exit_code must be an integer or null")
    started = _parse_timestamp(record.get("started_at"), field="started_at")
    ended = _parse_timestamp(record.get("ended_at"), field="ended_at")
    if ended < started:
        raise ScannerReportError("ended_at must not precede started_at")
    _safe_artifact_ref(record.get("normalized_result_ref"), field="normalized_result_ref")
    _safe_artifact_ref(record.get("scanner_index_ref"), field="scanner_index_ref")
    if list(iter_secret_findings(record, field_path="scanner_run")):
        raise ScannerReportError("scanner run record contains an unredacted secret-like value")


def validate_scanner_runs_report(report: dict[str, Any]) -> None:
    expected_keys = {"schema_version", "run_id", "repo", "generated_at", "source", "safety", "summary", "runs"}
    if not isinstance(report, dict) or set(report) != expected_keys:
        raise ScannerReportError("scanner-runs.json fields do not match the public-safe contract")
    if report.get("schema_version") != SCHEMA_VERSION or report.get("source") != "local-scanner-execution":
        raise ScannerReportError("scanner-runs.json version or source is invalid")
    _safe_text(report.get("run_id"), field="run_id")
    if report.get("repo"):
        _safe_text(report.get("repo"), field="repo")
    _parse_timestamp(report.get("generated_at"), field="scanner-runs.json generated_at")
    if report.get("safety") != {
        "public_safe": True,
        "raw_scanner_bodies_copied": False,
        "secret_values_copied": False,
        "review_only": True,
    }:
        raise ScannerReportError("scanner-runs.json safety flags are invalid")
    runs = report.get("runs")
    if not isinstance(runs, list) or len(runs) > MAX_SCANNER_RUNS:
        raise ScannerReportError(f"scanner-runs.json is limited to {MAX_SCANNER_RUNS} records")
    for record in runs:
        validate_scanner_run_record(record)
    if report.get("summary") != _summary(runs):
        raise ScannerReportError("scanner-runs.json summary does not match its records")
    if list(iter_secret_findings(report, field_path="scanner_runs")):
        raise ScannerReportError("scanner run report contains an unredacted secret-like value")


def _validate_run_artifact(
    run_dir: Path,
    value: str,
    *,
    field: str,
    required_root: Path,
    exact_path: Path | None = None,
) -> None:
    run_root = run_dir.resolve(strict=False)
    rel = Path(value)
    if exact_path is not None and rel != exact_path:
        raise ScannerReportError(f"{field} must reference {exact_path.as_posix()}")
    if exact_path is None and (rel == required_root or required_root not in rel.parents):
        raise ScannerReportError(f"{field} must stay under {required_root.as_posix()}")
    current = run_root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ScannerReportError(f"{field} must not contain symlink components")
    target = run_root / rel
    try:
        target.resolve(strict=True).relative_to(run_root)
    except (FileNotFoundError, ValueError) as exc:
        raise ScannerReportError(f"{field} must reference an existing contained artifact") from exc
    if not target.is_file():
        raise ScannerReportError(f"{field} must reference a regular file")


def validate_scanner_run_artifacts(run_dir: Path, record: dict[str, Any]) -> None:
    """Validate scanner-run references against this run's configured reports directory."""

    validate_scanner_run_record(record)
    run_root = run_dir.resolve(strict=False)
    try:
        reports_rel = reports_dir(run_root).relative_to(run_root)
    except (OSError, ValueError) as exc:
        raise ScannerReportError("scanner run reports_dir is invalid") from exc
    scanner_results = reports_rel / "scanner-results"
    normalized_root = scanner_results / "normalized"
    normalized_ref = record.get("normalized_result_ref")
    if normalized_ref is not None:
        _validate_run_artifact(
            run_root,
            normalized_ref,
            field="normalized_result_ref",
            required_root=normalized_root,
        )
    index_ref = record.get("scanner_index_ref")
    if index_ref is not None:
        _validate_run_artifact(
            run_root,
            index_ref,
            field="scanner_index_ref",
            required_root=scanner_results,
            exact_path=scanner_results / "scanner-index.json",
        )


def validate_scanner_runs_for_run(run_dir: Path, report: dict[str, Any]) -> None:
    """Validate public-safe report shape and every run-aware artifact reference."""

    validate_scanner_runs_report(report)
    for record in report["runs"]:
        validate_scanner_run_artifacts(run_dir, record)


def successful_scanner_run_exists(run_dir: Path, *, adapter_id: str) -> bool:
    json_path, _ = preflight_scanner_reports(run_dir)
    existing = _load_existing(json_path)
    successful = bool(
        existing
        and any(
            isinstance(record, dict)
            and record.get("adapter_id") == adapter_id
            and record.get("status") == "succeeded"
            for record in existing.get("runs") or []
        )
    )
    if successful:
        # Preserve immutable-history detection even if an operator has deleted
        # the referenced artifacts; the caller must reject a same-run rerun.
        return True
    if existing is not None:
        validate_scanner_runs_for_run(run_dir, existing)
    return False


def build_scanner_run_record(
    *,
    adapter_id: str,
    tool_version: str,
    image: str,
    status: str,
    scanner_status: str,
    started_at: str,
    ended_at: str,
    duration_ms: int,
    scanner_exit_code: int | None,
    result_count: int,
    normalized_leads_count: int,
    redaction_count: int,
    sandbox_profile: str,
    runtime: str | None,
    network_accessed: bool,
    result_classification: str,
    normalized_result_ref: str | None,
    scanner_index_ref: str | None,
) -> dict[str, Any]:
    if status not in SCANNER_RUN_STATUSES:
        raise ScannerReportError("scanner run status is invalid")
    if network_accessed:
        raise ScannerReportError("scanner run reports only support offline execution")
    for field, value in {
        "duration_ms": duration_ms,
        "result_count": result_count,
        "normalized_leads_count": normalized_leads_count,
        "redaction_count": redaction_count,
    }.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ScannerReportError(f"{field} must be a non-negative integer")
    digest = image.partition("@sha256:")[2]
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ScannerReportError("scanner image must use an immutable sha256 digest")
    record = {
        "id": f"scan-{uuid.uuid4()}",
        "adapter_id": _safe_text(adapter_id, field="adapter_id"),
        "tool_version": _safe_text(tool_version, field="tool_version"),
        "image_digest": f"sha256:{digest}",
        "status": status,
        "scanner_status": _safe_text(scanner_status, field="scanner_status"),
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "scanner_exit_code": scanner_exit_code,
        "result_count": result_count,
        "normalized_leads_count": normalized_leads_count,
        "redaction_count": redaction_count,
        "sandbox_profile": _safe_text(sandbox_profile, field="sandbox_profile"),
        "runtime": _safe_text(runtime, field="runtime"),
        "network_accessed": False,
        "result_classification": _safe_text(result_classification, field="result_classification"),
        "finding_status": "review-only",
        "normalized_result_ref": _safe_artifact_ref(normalized_result_ref, field="normalized_result_ref"),
        "scanner_index_ref": _safe_artifact_ref(scanner_index_ref, field="scanner_index_ref"),
    }
    validate_scanner_run_record(record)
    return record


def _summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(item.get("status") or "unknown") for item in runs)
    adapter_counts = Counter(str(item.get("adapter_id") or "unknown") for item in runs)
    durations = [int(item.get("duration_ms") or 0) for item in runs]
    return {
        "run_count": len(runs),
        "by_status": dict(sorted(status_counts.items())),
        "by_adapter": dict(sorted(adapter_counts.items())),
        "total_duration_ms": sum(durations),
        "maximum_duration_ms": max(durations, default=0),
        "result_count": sum(int(item.get("result_count") or 0) for item in runs),
        "normalized_leads_count": sum(int(item.get("normalized_leads_count") or 0) for item in runs),
        "redaction_count": sum(int(item.get("redaction_count") or 0) for item in runs),
    }


def render_scanner_runs_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Scanner Runs",
        "",
        "Public-safe scanner execution metadata. Raw scanner bodies and secret values are intentionally excluded.",
        "All scanner output remains review-only until repository-context validation confirms a finding.",
        "",
        f"- Run ID: `{report.get('run_id', '')}`",
        f"- Repository: `{report.get('repo', '')}`",
        f"- Generated at: `{report.get('generated_at', '')}`",
        f"- Scanner executions: {summary.get('run_count', 0)}",
        f"- Total duration: {summary.get('total_duration_ms', 0)} ms",
        f"- Normalized leads: {summary.get('normalized_leads_count', 0)}",
        f"- Redactions: {summary.get('redaction_count', 0)}",
        "",
        "## Executions",
        "",
        "| Adapter | Version | Status | Scanner status | Duration ms | Results | Normalized leads | Redactions |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for item in report.get("runs") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| {item.get('adapter_id', '')} | {item.get('tool_version', '')} | {item.get('status', '')} | "
            f"{item.get('scanner_status', '')} | {item.get('duration_ms', 0)} | {item.get('result_count', 0)} | "
            f"{item.get('normalized_leads_count', 0)} | {item.get('redaction_count', 0)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        fd = os.open(temporary, flags, 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ScannerReportError("scanner report temporary path must be a regular file")
        data = content.encode("utf-8")
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise ScannerReportError("scanner report write made no progress")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = None
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ScannerReportError("scanner report destination must be a regular non-symlink file")
        os.replace(temporary, path)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def append_scanner_run(run_dir: Path, record: dict[str, Any]) -> tuple[dict[str, Any], Path, Path]:
    validate_scanner_run_record(record)
    json_path, markdown_path = preflight_scanner_reports(run_dir)
    lock_path = json_path.with_name(f".{json_path.name}.lock")
    deadline = time.monotonic() + 10.0
    while True:
        try:
            os.mkdir(lock_path, 0o700)
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise ScannerReportError("timed out waiting for scanner report lock") from exc
            time.sleep(0.01)
    try:
        existing = _load_existing(json_path)
        ctx = load_context(run_dir)
        runs = list(existing.get("runs") or []) if existing else []
        for existing_record in runs:
            validate_scanner_run_record(existing_record)
        runs.append(record)
        if len(runs) > MAX_SCANNER_RUNS:
            raise ScannerReportError(f"scanner-runs.json is limited to {MAX_SCANNER_RUNS} records")
        report = {
            "schema_version": SCHEMA_VERSION,
            "run_id": _safe_text(ctx.get("run_id") or run_dir.name, field="run_id"),
            "repo": "" if not ctx.get("repo") else _safe_text(ctx.get("repo"), field="repo"),
            "generated_at": utc_now(),
            "source": "local-scanner-execution",
            "safety": {
                "public_safe": True,
                "raw_scanner_bodies_copied": False,
                "secret_values_copied": False,
                "review_only": True,
            },
            "summary": _summary(runs),
            "runs": runs,
        }
        validate_scanner_runs_for_run(run_dir, report)
        _atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        _atomic_write(markdown_path, render_scanner_runs_markdown(report))
        return report, json_path, markdown_path
    finally:
        try:
            os.rmdir(lock_path)
        except FileNotFoundError:
            pass
