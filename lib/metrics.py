from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from gralib import load_context, utc_now, write_json
from duplicate_decisions import duplicate_decision_metrics
from issue_ledger import ledger_metrics
from workflow_profile import summarize_workflow_profile

COUNT_STATUSES = [
    "Confirmed",
    "Probable",
    "Potential",
    "Needs human review",
    "Informational",
    "Invalid",
    "Unknown",
]
SEVERITIES = ["Critical", "High", "Medium", "Low", "Informational", "Unknown"]
VALIDATION_DECISIONS = ["confirm", "downgrade", "invalidate", "needs-human-review", "unknown"]
TRACE_VALUES = ["Confirmed", "Probable", "Potential", "Invalid", "Not assessed"]
PROOF_TYPES = [
    "static-trace",
    "unit-test-plan",
    "local-regression-test",
    "config-check",
    "parser-only-local-input",
    "mocked-local-service",
    "unknown",
]
PROOF_STATUSES = ["confirmed", "failed", "not-run", "needs-human-review", "unknown"]
TARGET_STATUSES = ["queued", "in_progress", "reviewed", "skipped", "needs_human_review", "unknown"]
ARTIFACT_KINDS = ["file", "dir", "unknown"]
ARTIFACT_RETENTIONS = ["latest", "supporting", "archive", "unknown"]
OBSERVABILITY_COMMANDS = ["gra-research", "gra-gapfill", "gra-validate-report", "unknown"]
OBSERVABILITY_PHASES = ["exec", "goal", "generate", "validate", "list", "unknown"]
RUN_TARGET_ID = "__run__"
UNKNOWN_TARGET_ID = "__unknown__"
TARGET_ID_RE = re.compile(r"^TGT-(?:[A-Z][A-Z0-9]*-)?[0-9]{3,}$")


class MetricsError(RuntimeError):
    pass


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_report_json(root: Path, rel: Path, default: Any = None) -> Any:
    path = root / rel
    current = root
    for part in rel.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            return default
    return load_json(path, default)


def counter_dict(counter: Counter[Any], ordered_keys: list[str] | None = None) -> dict[str, int]:
    result: dict[str, int] = {}
    if ordered_keys:
        for key in ordered_keys:
            result[key] = int(counter.get(key, 0))
    for key, value in sorted(counter.items(), key=lambda item: str(item[0])):
        normalized = str(key or "Unknown")
        if normalized not in result:
            result[normalized] = int(value)
    return result


def safe_label(value: Any, allowed: list[str], unknown: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return unknown


def count_known(items: list[dict[str, Any]], field: str, allowed: list[str], unknown: str) -> dict[str, int]:
    return counter_dict(
        Counter(safe_label(item.get(field), allowed, unknown) for item in items),
        allowed,
    )


def reports_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    raw = Path(str(ctx.get("reports_dir", "reports") or "reports"))
    if raw.is_absolute() or ".." in raw.parts:
        raise MetricsError(f"reports_dir must be a relative path under the run directory: {raw}")
    reports = run_dir / raw
    current = run_dir
    for part in raw.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise MetricsError(f"reports_dir must not contain symlink components: {raw}")
    return reports


def list_of_dicts(data: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    values = data.get(key)
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict)]


def load_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSONL record: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected JSON object")
        records.append(value)
    return records


def rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def finding_metrics(findings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(findings),
        "by_severity": count_known(findings, "severity", SEVERITIES, "Unknown"),
        "by_status": count_known(findings, "status", COUNT_STATUSES, "Unknown"),
        "issue_recommended": sum(1 for f in findings if f.get("issue_recommended") is True),
        "chain_membership_count": sum(
            len(f.get("chain_membership") or [])
            for f in findings
            if isinstance(f.get("chain_membership") or [], list)
        ),
    }


def validation_metrics(validations: list[dict[str, Any]], present: bool) -> dict[str, Any]:
    decisions = Counter(safe_label(item.get("decision"), VALIDATION_DECISIONS, "unknown") for item in validations)
    downgrade_or_invalidate = int(decisions.get("downgrade", 0) + decisions.get("invalidate", 0))
    blocking = int(downgrade_or_invalidate + decisions.get("needs-human-review", 0))
    return {
        "artifact_present": present,
        "total": len(validations),
        "by_decision": counter_dict(decisions, VALIDATION_DECISIONS),
        "downgrade_or_invalidate_count": downgrade_or_invalidate,
        "downgrade_or_invalidate_rate": rate(downgrade_or_invalidate, len(validations)),
        "blocking_decision_count": blocking,
    }


def chain_metrics(chains: list[dict[str, Any]], present: bool) -> dict[str, Any]:
    return {
        "artifact_present": present,
        "total": len(chains),
        "by_status": count_known(chains, "status", COUNT_STATUSES, "Unknown"),
        "by_severity": count_known(chains, "severity", SEVERITIES, "Unknown"),
    }


def proof_metrics(proofs: list[dict[str, Any]], present: bool) -> dict[str, Any]:
    return {
        "artifact_present": present,
        "total": len(proofs),
        "by_type": count_known(proofs, "proof_type", PROOF_TYPES, "unknown"),
        "by_status": count_known(proofs, "status", PROOF_STATUSES, "unknown"),
    }


def gapfill_metrics(
    targets: list[dict[str, Any]],
    gapfill_data: Any,
    coverage_present: bool,
    gapfill_present: bool,
) -> dict[str, Any]:
    gapfill_targets = [
        t
        for t in targets
        if str(t.get("id", "")).startswith("TGT-GAPFILL-") or t.get("category") == "gapfill"
    ]
    recommended = 0
    for target in targets:
        coverage = target.get("coverage") if isinstance(target.get("coverage"), dict) else {}
        if coverage.get("gapfill_recommended") is True:
            recommended += 1
    current_candidate_count = 0
    current_generated_count = 0
    current_new_count = 0
    current_reused_count = 0
    if isinstance(gapfill_data, dict):
        current_run = gapfill_data.get("current_run") if isinstance(gapfill_data.get("current_run"), dict) else {}
        candidate_count = current_run.get("candidate_count", gapfill_data.get("candidate_count"))
        if isinstance(candidate_count, int) and not isinstance(candidate_count, bool):
            current_candidate_count = max(0, int(candidate_count))
        generated_count = current_run.get("generated_target_count", gapfill_data.get("generated_target_count"))
        if isinstance(generated_count, int) and not isinstance(generated_count, bool):
            current_generated_count = max(0, int(generated_count))
        generated = gapfill_data.get("generated_targets")
        if current_generated_count == 0 and isinstance(generated, list):
            current_generated_count = len([item for item in generated if isinstance(item, dict)])
        new_count = current_run.get("new_target_count")
        if isinstance(new_count, int) and not isinstance(new_count, bool):
            current_new_count = max(0, int(new_count))
        reused_count = current_run.get("reused_target_count")
        if isinstance(reused_count, int) and not isinstance(reused_count, bool):
            current_reused_count = max(0, int(reused_count))
    cumulative_generated = len(gapfill_targets)
    cumulative_reviewed = sum(1 for t in gapfill_targets if t.get("status") == "reviewed")
    if isinstance(gapfill_data, dict):
        cumulative_data = gapfill_data.get("cumulative") if isinstance(gapfill_data.get("cumulative"), dict) else {}
        generated_total = cumulative_data.get("generated_target_count")
        if isinstance(generated_total, int) and not isinstance(generated_total, bool):
            cumulative_generated = max(cumulative_generated, int(generated_total))
        reviewed_total = cumulative_data.get("reviewed_target_count")
        if isinstance(reviewed_total, int) and not isinstance(reviewed_total, bool):
            cumulative_reviewed = max(cumulative_reviewed, int(reviewed_total))
    cumulative_by_status = count_known(gapfill_targets, "status", TARGET_STATUSES, "unknown")
    return {
        "coverage_artifact_present": coverage_present,
        "gapfill_artifact_present": gapfill_present,
        "source_targets_recommended": recommended,
        "current_run": {
            "candidate_count": current_candidate_count,
            "generated_target_count": current_generated_count,
            "new_target_count": current_new_count,
            "reused_target_count": current_reused_count,
        },
        "cumulative": {
            "generated_target_count": cumulative_generated,
            "reviewed_target_count": cumulative_reviewed,
            "targets_by_status": cumulative_by_status,
        },
        # Backward-compatible cumulative aliases.
        "targets_generated": cumulative_generated,
        "targets_reviewed": cumulative_reviewed,
        "targets_by_status": cumulative_by_status,
    }


def trace_metrics(traces: list[dict[str, Any]], present: bool) -> dict[str, Any]:
    return {
        "artifact_present": present,
        "total": len(traces),
        "by_reachable": count_known(traces, "reachable", TRACE_VALUES, "Not assessed"),
        "by_attacker_control": count_known(traces, "attacker_control", TRACE_VALUES, "Not assessed"),
        "by_status": count_known(traces, "status", COUNT_STATUSES, "Unknown"),
    }


def safe_target_id(value: Any) -> str:
    if value is None or value == "":
        return RUN_TARGET_ID
    text = str(value)
    if TARGET_ID_RE.fullmatch(text):
        return text
    return UNKNOWN_TARGET_ID


def safe_exit_code(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return -1


def safe_duration_ms(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return int(value)
    return 0


def target_ids_by_index(targets: list[dict[str, Any]]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for index, target in enumerate(targets):
        mapping[index] = safe_target_id(target.get("id"))
    return mapping


def taxonomy_normalization_target(event: dict[str, Any], target_index: dict[int, str]) -> str:
    field_path = event.get("field_path")
    if isinstance(field_path, str):
        match = re.match(r"^targets\.targets\[(\d+)\]", field_path)
        if match:
            return target_index.get(int(match.group(1)), UNKNOWN_TARGET_ID)
        if field_path.startswith("findings."):
            return "__findings__"
    return RUN_TARGET_ID


def observability_metrics(
    *,
    command_events: list[dict[str, Any]],
    command_events_present: bool,
    taxonomy_normalizations: list[dict[str, Any]],
    taxonomy_normalizations_present: bool,
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    durations: list[dict[str, Any]] = []
    command_counts: Counter[str] = Counter()
    phase_counts: Counter[str] = Counter()
    exit_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()
    failures_by_target: Counter[str] = Counter()
    grouped_event_counts: Counter[tuple[str, str, str]] = Counter()
    validation_counts: Counter[str] = Counter()

    for event in command_events:
        command = safe_label(event.get("command"), OBSERVABILITY_COMMANDS, "unknown")
        phase = safe_label(event.get("phase"), OBSERVABILITY_PHASES, "unknown")
        target_id = safe_target_id(event.get("target_id"))
        duration_ms = safe_duration_ms(event.get("duration_ms"))
        exit_code = safe_exit_code(event.get("exit_code"))
        duration_record = {
            "target_id": target_id,
            "command": command,
            "phase": phase,
            "duration_ms": duration_ms,
            "exit_code": exit_code,
        }
        durations.append(duration_record)
        command_counts[command] += 1
        phase_counts[phase] += 1
        exit_counts[str(exit_code)] += 1
        target_counts[target_id] += 1
        grouped_event_counts[(target_id, command, phase)] += 1
        if exit_code != 0:
            failures_by_target[target_id] += 1
        if command == "gra-validate-report":
            validation_counts[target_id] += 1

    durations.sort(key=lambda item: (-int(item["duration_ms"]), str(item["target_id"]), str(item["command"])))

    reruns_by_target: Counter[str] = Counter()
    for (target_id, _command, _phase), count in grouped_event_counts.items():
        if count > 1:
            reruns_by_target[target_id] += count - 1

    validation_retries_by_target = {
        target_id: count - 1
        for target_id, count in sorted(validation_counts.items())
        if count > 1
    }

    target_index = target_ids_by_index(targets)
    normalizations_by_target = Counter(
        taxonomy_normalization_target(event, target_index)
        for event in taxonomy_normalizations
    )

    return {
        "command_events_present": command_events_present,
        "total_events": len(command_events),
        "by_command": counter_dict(command_counts, OBSERVABILITY_COMMANDS),
        "by_phase": counter_dict(phase_counts, OBSERVABILITY_PHASES),
        "by_exit_code": counter_dict(exit_counts),
        "execution_durations": durations,
        "failures_by_target": counter_dict(failures_by_target),
        "reruns_by_target": counter_dict(reruns_by_target),
        "events_by_target": counter_dict(target_counts),
        "validation_retry_count": sum(validation_retries_by_target.values()),
        "validation_retries_by_target": validation_retries_by_target,
        "taxonomy_normalizations_present": taxonomy_normalizations_present,
        "taxonomy_normalization_count": len(taxonomy_normalizations),
        "taxonomy_normalizations_by_target": counter_dict(normalizations_by_target),
    }


def warnings_from(value: Any) -> int:
    if isinstance(value, dict):
        count = 0
        for key, item in value.items():
            if key == "warnings" and isinstance(item, list):
                count += len(item)
            else:
                count += warnings_from(item)
        return count
    if isinstance(value, list):
        return sum(warnings_from(item) for item in value)
    return 0


def issue_plan_metrics(plan: Any, present: bool) -> dict[str, Any]:
    selected = []
    if isinstance(plan, dict):
        selected = [item for item in plan.get("selected_findings") or [] if isinstance(item, dict)]
    return {
        "artifact_present": present,
        "selected_findings": len(selected),
        "warning_count": warnings_from(plan),
    }


def evidence_graph_compact_summary(graph: Any) -> dict[str, Any]:
    nodes = []
    edges = []
    if isinstance(graph, dict):
        nodes = [item for item in graph.get("nodes") or [] if isinstance(item, dict)]
        edges = [item for item in graph.get("edges") or [] if isinstance(item, dict)]
    return {
        "artifact_present": isinstance(graph, dict),
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def benchmark_compact_summary(benchmark: Any) -> dict[str, Any]:
    gates = []
    summary = {}
    if isinstance(benchmark, dict):
        gates = [item for item in benchmark.get("quality_gates") or [] if isinstance(item, dict)]
        summary = benchmark.get("summary") if isinstance(benchmark.get("summary"), dict) else {}
    statuses = Counter(str(item.get("status") or "unknown") for item in gates)
    return {
        "artifact_present": isinstance(benchmark, dict),
        "overall_status": str(summary.get("overall_status") or "not-available"),
        "gate_count": int(summary.get("gate_count") if isinstance(summary.get("gate_count"), int) else len(gates)),
        "passed": int(summary.get("passed") if isinstance(summary.get("passed"), int) else statuses.get("pass", 0)),
        "warnings": int(summary.get("warnings") if isinstance(summary.get("warnings"), int) else statuses.get("warn", 0)),
        "failed": int(summary.get("failed") if isinstance(summary.get("failed"), int) else statuses.get("fail", 0)),
    }


def scanner_compact_summary(scanner_index: Any) -> dict[str, Any]:
    results = []
    if isinstance(scanner_index, dict):
        results = [item for item in scanner_index.get("results") or [] if isinstance(item, dict)]
    normalized_leads = 0
    for item in results:
        count = item.get("normalized_leads_count")
        if isinstance(count, int) and not isinstance(count, bool) and count > 0:
            normalized_leads += count
    return {
        "artifact_present": isinstance(scanner_index, dict),
        "result_count": len(results),
        "normalized_leads_count": normalized_leads,
    }


def compact_public_summary(
    *,
    findings_data: Any,
    findings: dict[str, Any],
    issue_publication_plan: dict[str, Any],
    issue_ledger: dict[str, Any],
    workflow_profile: dict[str, Any],
    evidence_graph: Any,
    benchmark: Any,
    scanner_index: Any,
) -> dict[str, Any]:
    no_findings = findings_data.get("no_findings") if isinstance(findings_data, dict) and isinstance(findings_data.get("no_findings"), dict) else {}
    no_findings_source_stage = str(no_findings.get("source_stage") or "")
    return {
        "public_safe": True,
        "notes": "Counts and status flags only; review repository names and aggregate counts before external reuse.",
        "findings_total": int(findings.get("total") or 0),
        "findings_by_severity": dict(findings.get("by_severity") or {}),
        "findings_by_status": dict(findings.get("by_status") or {}),
        "issue_recommended_findings": int(findings.get("issue_recommended") or 0),
        "issue_publication_warning_count": int(issue_publication_plan.get("warning_count") or 0),
        "issue_ledger_published_findings": int(issue_ledger.get("published_findings") or 0),
        "issue_ledger_drift_warning_count": int(issue_ledger.get("drift_warning_count") or 0),
        "workflow_profile": dict(workflow_profile),
        "evidence_graph": evidence_graph_compact_summary(evidence_graph),
        "benchmark": benchmark_compact_summary(benchmark),
        "scanner": scanner_compact_summary(scanner_index),
        "no_findings": {
            "recorded": bool(no_findings),
            "source_stage": no_findings_source_stage,
            "recon_only": no_findings_source_stage == "recon",
        },
    }


def parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def run_duration_metrics(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        return {"available": False, "seconds": None, "source": "not-available"}
    execution = manifest.get("execution") if isinstance(manifest.get("execution"), dict) else {}
    duration = execution.get("duration_seconds")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0:
        return {
            "available": True,
            "seconds": round(float(duration), 3),
            "source": "run-manifest.execution.duration_seconds",
        }
    start = parse_time(execution.get("started_at") or manifest.get("started_at"))
    end = parse_time(execution.get("finished_at") or execution.get("completed_at") or manifest.get("finished_at"))
    if start and end and end >= start:
        return {
            "available": True,
            "seconds": round((end - start).total_seconds(), 3),
            "source": "run-manifest timestamps",
        }
    return {"available": False, "seconds": None, "source": "not-available"}


def artifact_metrics(run_dir: Path, reports: Path, manifest: Any) -> dict[str, Any]:
    manifest_artifacts = []
    if isinstance(manifest, dict) and isinstance(manifest.get("artifacts"), list):
        manifest_artifacts = [item for item in manifest["artifacts"] if isinstance(item, dict)]
    retention_summary = manifest.get("artifact_retention") if isinstance(manifest, dict) and isinstance(manifest.get("artifact_retention"), dict) else {}
    latest_summary = retention_summary.get("latest_status_artifacts")
    archive_summary = retention_summary.get("archive_artifacts")
    hygiene_warnings = 0
    if "latest_status_artifacts" in retention_summary and not isinstance(latest_summary, list):
        hygiene_warnings += 1
    if "archive_artifacts" in retention_summary and not isinstance(archive_summary, list):
        hygiene_warnings += 1
    latest_paths = (
        {str(path) for path in latest_summary if isinstance(path, str)}
        if isinstance(latest_summary, list)
        else set()
    )
    archive_paths = (
        {str(path) for path in archive_summary if isinstance(path, str)}
        if isinstance(archive_summary, list)
        else set()
    )
    artifact_paths = {str(item.get("path") or "") for item in manifest_artifacts}
    retention_by_path = {str(item.get("path") or ""): item.get("retention") for item in manifest_artifacts}
    for path in latest_paths:
        if path not in artifact_paths:
            hygiene_warnings += 1
        elif retention_by_path.get(path) != "latest":
            hygiene_warnings += 1
    for path in archive_paths:
        if path not in artifact_paths:
            hygiene_warnings += 1
        elif retention_by_path.get(path) != "archive":
            hygiene_warnings += 1
    for item in manifest_artifacts:
        retention = item.get("retention")
        path = str(item.get("path") or "")
        if retention not in {"latest", "supporting", "archive"}:
            hygiene_warnings += 1
        elif retention == "latest" and path not in latest_paths:
            hygiene_warnings += 1
        elif retention == "archive" and path not in archive_paths:
            hygiene_warnings += 1
    report_files = 0
    report_dirs = 0
    if reports.exists():
        pending = [reports]
        while pending:
            directory = pending.pop()
            for path in directory.iterdir():
                if path.is_symlink():
                    continue
                if path.is_file():
                    report_files += 1
                elif path.is_dir():
                    report_dirs += 1
                    pending.append(path)
    return {
        "manifest_present": isinstance(manifest, dict),
        "manifest_artifact_total": len(manifest_artifacts),
        "manifest_by_kind": counter_dict(
            Counter(safe_label(item.get("kind"), ARTIFACT_KINDS, "unknown") for item in manifest_artifacts),
            ARTIFACT_KINDS,
        ),
        "manifest_by_retention": counter_dict(
            Counter(safe_label(item.get("retention"), ARTIFACT_RETENTIONS, "unknown") for item in manifest_artifacts),
            ARTIFACT_RETENTIONS,
        ),
        "latest_status_artifact_count": len(latest_paths),
        "archive_artifact_count": len(archive_paths),
        "manifest_hygiene_warnings": hygiene_warnings,
        "reports_file_count": report_files,
        "reports_dir_count": report_dirs,
    }


def build_metrics(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if not (run_dir / "context.json").exists():
        raise MetricsError(f"context.json not found under {run_dir}")
    ctx = load_context(run_dir)
    reports = reports_dir(run_dir)
    findings_data = load_json(reports / "findings.json", {}) or {}
    targets_data = load_json(reports / "targets.json", {}) or {}
    validation_data = load_json(reports / "validation.json", None)
    chains_data = load_json(reports / "chains.json", None)
    proofs_data = load_json(reports / "proofs.json", None)
    traces_data = load_json(reports / "traces.json", None)
    gapfill_data = load_json(reports / "gapfill-targets.json", None)
    issue_plan = load_json(reports / "issue-publication-plan.json", None)
    issue_ledger = load_json(reports / "issue-ledger.json", None)
    workflow_profile_data = load_report_json(reports, Path("workflow-profile.json"), None)
    evidence_graph = load_report_json(reports, Path("evidence-graph.json"), None)
    benchmark = load_report_json(reports, Path("benchmark.json"), None)
    scanner_index = load_report_json(reports, Path("scanner-results") / "scanner-index.json", None)
    command_events_path = reports / "command-events.jsonl"
    command_events = load_jsonl_objects(command_events_path)
    taxonomy_normalizations_path = reports / "taxonomy-normalizations.jsonl"
    taxonomy_normalizations = load_jsonl_objects(taxonomy_normalizations_path)
    duplicate_decisions_present = (reports / "duplicate-decisions").is_dir()
    duplicate_decisions = []
    if duplicate_decisions_present:
        duplicate_decisions = [
            load_json(path, {})
            for path in sorted((reports / "duplicate-decisions").glob("*.json"))
        ]
    manifest = load_json(run_dir / "run-manifest.json", None)

    findings = list_of_dicts(findings_data, "findings")
    targets = list_of_dicts(targets_data, "targets")
    validations = list_of_dicts(validation_data, "validations")
    chains = list_of_dicts(chains_data, "chains")
    proofs = list_of_dicts(proofs_data, "proofs")
    traces = list_of_dicts(traces_data, "traces")
    findings_metrics = finding_metrics(findings)
    validation_summary = validation_metrics(validations, validation_data is not None)
    chains_summary = chain_metrics(chains, chains_data is not None)
    proofs_summary = proof_metrics(proofs, proofs_data is not None)
    gapfill_summary = gapfill_metrics(
        targets,
        gapfill_data,
        (reports / "COVERAGE.md").exists(),
        gapfill_data is not None,
    )
    traces_summary = trace_metrics(traces, traces_data is not None)
    issue_plan_summary = issue_plan_metrics(issue_plan, issue_plan is not None)
    issue_ledger_summary = ledger_metrics(issue_ledger, issue_ledger is not None)
    workflow_profile_summary = summarize_workflow_profile(workflow_profile_data)
    duplicate_decisions_summary = duplicate_decision_metrics(duplicate_decisions, duplicate_decisions_present)
    observability_summary = observability_metrics(
        command_events=command_events,
        command_events_present=command_events_path.exists(),
        taxonomy_normalizations=taxonomy_normalizations,
        taxonomy_normalizations_present=taxonomy_normalizations_path.exists(),
        targets=targets,
    )
    artifacts_summary = artifact_metrics(run_dir, reports, manifest)
    duration_summary = run_duration_metrics(manifest)

    return {
        "schema_version": "1",
        "run_id": str(ctx.get("run_id", run_dir.name)),
        "repo": str(ctx.get("repo", "")),
        "branch": ctx.get("branch", ""),
        "commit": ctx.get("commit", ""),
        "generated_at": utc_now(),
        "source": "local-report-artifacts",
        "safety": {
            "local_artifacts_only": True,
            "raw_evidence_copied": False,
            "secrets_copied": False,
            "notes": "Counts only; finding evidence, issue body text, proof evidence, and trace evidence are not copied.",
        },
        "summary": compact_public_summary(
            findings_data=findings_data,
            findings=findings_metrics,
            issue_publication_plan=issue_plan_summary,
            issue_ledger=issue_ledger_summary,
            workflow_profile=workflow_profile_summary,
            evidence_graph=evidence_graph,
            benchmark=benchmark,
            scanner_index=scanner_index,
        ),
        "findings": findings_metrics,
        "adversarial_validation": validation_summary,
        "chains": chains_summary,
        "proofs": proofs_summary,
        "gapfill": gapfill_summary,
        "traces": traces_summary,
        "issue_publication_plan": issue_plan_summary,
        "issue_ledger": issue_ledger_summary,
        "workflow_profile": workflow_profile_summary,
        "duplicate_decisions": duplicate_decisions_summary,
        "observability": observability_summary,
        "artifacts": artifacts_summary,
        "run_duration": duration_summary,
    }


def markdown_counts(title: str, counts: dict[str, int]) -> list[str]:
    lines = [f"### {title}", "", "| Value | Count |", "|---|---:|"]
    for key, value in counts.items():
        lines.append(f"| {key} | {value} |")
    lines.append("")
    return lines


def render_metrics_markdown(metrics: dict[str, Any]) -> str:
    safety_summary = (
        "This report intentionally excludes raw finding evidence, issue body text, proof evidence, trace evidence, and "
        + "secret values."
    )
    compact = metrics.get("summary") if isinstance(metrics.get("summary"), dict) else {}
    evidence = compact.get("evidence_graph") if isinstance(compact.get("evidence_graph"), dict) else {}
    benchmark = compact.get("benchmark") if isinstance(compact.get("benchmark"), dict) else {}
    scanner = compact.get("scanner") if isinstance(compact.get("scanner"), dict) else {}
    no_findings = compact.get("no_findings") if isinstance(compact.get("no_findings"), dict) else {}
    workflow_profile = compact.get("workflow_profile") if isinstance(compact.get("workflow_profile"), dict) else {}
    lines = [
        "# Advanced Workflow Metrics",
        "",
        "Local-only counts for advanced GenAI Repo Auditor workflow artifacts.",
        safety_summary,
        "",
        f"- Run ID: `{metrics.get('run_id', '')}`",
        f"- Repository: `{metrics.get('repo', '')}`",
        f"- Commit: `{metrics.get('commit', '')}`",
        f"- Generated at: `{metrics.get('generated_at', '')}`",
        f"- Source: `{metrics.get('source', '')}`",
        "",
        "## Public-safe compact summary",
        "",
        "These counts are designed for dogfood reports after human review; they do not include finding bodies, raw evidence, proof payloads, scanner lead bodies, or issue draft text.",
        "",
        "| Field | Value |",
        "|---|---:|",
        f"| Findings total | {compact.get('findings_total', 0)} |",
        f"| Issue-recommended findings | {compact.get('issue_recommended_findings', 0)} |",
        f"| Issue-publication warnings | {compact.get('issue_publication_warning_count', 0)} |",
        f"| Published findings in ledger | {compact.get('issue_ledger_published_findings', 0)} |",
        f"| Issue ledger drift warnings | {compact.get('issue_ledger_drift_warning_count', 0)} |",
        f"| Workflow profile recorded | {str(bool(workflow_profile.get('artifact_present'))).lower()} |",
        f"| Stages skipped by scope | {workflow_profile.get('skipped_by_scope_count', 0)} |",
        f"| Evidence graph nodes | {evidence.get('node_count', 0)} |",
        f"| Evidence graph edges | {evidence.get('edge_count', 0)} |",
        f"| Benchmark gates | {benchmark.get('gate_count', 0)} |",
        f"| Benchmark warnings | {benchmark.get('warnings', 0)} |",
        f"| Benchmark failures | {benchmark.get('failed', 0)} |",
        f"| Scanner results | {scanner.get('result_count', 0)} |",
        f"| Normalized scanner leads | {scanner.get('normalized_leads_count', 0)} |",
        f"| No-findings record present | {str(bool(no_findings.get('recorded'))).lower()} |",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Findings | {metrics['findings']['total']} |",
        f"| Issue-recommended findings | {metrics['findings']['issue_recommended']} |",
        f"| Adversarial validations | {metrics['adversarial_validation']['total']} |",
        f"| Downgrade / invalidate rate | {metrics['adversarial_validation']['downgrade_or_invalidate_rate']:.4f} |",
        f"| Chains | {metrics['chains']['total']} |",
        f"| Proofs | {metrics['proofs']['total']} |",
        f"| Gapfill current candidates | {metrics['gapfill']['current_run']['candidate_count']} |",
        f"| Gapfill current generated/reused targets | {metrics['gapfill']['current_run']['generated_target_count']} |",
        f"| Gapfill cumulative generated targets | {metrics['gapfill']['cumulative']['generated_target_count']} |",
        f"| Traces | {metrics['traces']['total']} |",
        f"| Issue plan warnings | {metrics['issue_publication_plan']['warning_count']} |",
        f"| Issue ledger published findings | {metrics['issue_ledger']['published_findings']} |",
        f"| Workflow profile stages skipped by scope | {metrics['workflow_profile']['skipped_by_scope_count']} |",
        f"| Duplicate decisions | {metrics['duplicate_decisions']['total']} |",
        f"| Command events | {metrics['observability']['total_events']} |",
        f"| Validation retries | {metrics['observability']['validation_retry_count']} |",
        f"| Taxonomy normalizations | {metrics['observability']['taxonomy_normalization_count']} |",
        f"| Report files | {metrics['artifacts']['reports_file_count']} |",
        "",
        "## Findings",
        "",
    ]
    lines.extend(markdown_counts("By severity", metrics["findings"]["by_severity"]))
    lines.extend(markdown_counts("By status", metrics["findings"]["by_status"]))
    lines.extend(["## Adversarial validation", ""])
    lines.extend(markdown_counts("Decisions", metrics["adversarial_validation"]["by_decision"]))
    lines.extend(["## Chains", ""])
    lines.extend(markdown_counts("Chain status", metrics["chains"]["by_status"]))
    lines.extend(markdown_counts("Chain severity", metrics["chains"]["by_severity"]))
    lines.extend(["## Proofs", ""])
    lines.extend(markdown_counts("Proof type", metrics["proofs"]["by_type"]))
    lines.extend(markdown_counts("Proof status", metrics["proofs"]["by_status"]))
    lines.extend(["## Gapfill", "", "| Metric | Count |", "|---|---:|"])
    lines.append(f"| Source targets recommended | {metrics['gapfill']['source_targets_recommended']} |")
    lines.append(f"| Current candidate count | {metrics['gapfill']['current_run']['candidate_count']} |")
    lines.append(f"| Current generated/reused targets | {metrics['gapfill']['current_run']['generated_target_count']} |")
    lines.append(f"| Current new targets | {metrics['gapfill']['current_run']['new_target_count']} |")
    lines.append(f"| Current reused targets | {metrics['gapfill']['current_run']['reused_target_count']} |")
    lines.append(f"| Cumulative generated targets | {metrics['gapfill']['cumulative']['generated_target_count']} |")
    lines.append(f"| Cumulative reviewed targets | {metrics['gapfill']['cumulative']['reviewed_target_count']} |")
    lines.append("")
    lines.extend(markdown_counts("Cumulative gapfill target status", metrics["gapfill"]["cumulative"]["targets_by_status"]))
    lines.extend(["## Traces", ""])
    lines.extend(markdown_counts("Trace reachable", metrics["traces"]["by_reachable"]))
    lines.extend(markdown_counts("Trace attacker control", metrics["traces"]["by_attacker_control"]))
    lines.extend(markdown_counts("Trace status", metrics["traces"]["by_status"]))
    lines.extend(["## Issue publication plan", "", "| Metric | Count |", "|---|---:|"])
    lines.append(f"| Selected findings | {metrics['issue_publication_plan']['selected_findings']} |")
    lines.append(f"| Warnings | {metrics['issue_publication_plan']['warning_count']} |")
    lines.append("")
    lines.extend(["## Issue ledger", "", "| Metric | Count |", "|---|---:|"])
    lines.append(f"| Tracked findings | {metrics['issue_ledger']['tracked_findings']} |")
    lines.append(f"| Published findings | {metrics['issue_ledger']['published_findings']} |")
    lines.append(f"| Drift warnings | {metrics['issue_ledger']['drift_warning_count']} |")
    lines.append("")
    lines.extend(markdown_counts("Publication status", metrics["issue_ledger"]["by_publication_status"]))
    lines.extend(["## Workflow profile", "", "| Metric | Value |", "|---|---:|"])
    lines.append(f"| Artifact present | {str(bool(metrics['workflow_profile']['artifact_present'])).lower()} |")
    lines.append(f"| Profile | {metrics['workflow_profile']['profile']} |")
    lines.append(f"| Stages | {metrics['workflow_profile']['stage_count']} |")
    lines.append(f"| Skipped by scope | {metrics['workflow_profile']['skipped_by_scope_count']} |")
    lines.append(f"| Failed stages | {metrics['workflow_profile']['failed_count']} |")
    lines.append("")
    lines.extend(markdown_counts("Workflow stage status", metrics["workflow_profile"]["by_status"]))
    lines.extend(["## Duplicate decisions", "", "| Metric | Count |", "|---|---:|"])
    lines.append(f"| Total | {metrics['duplicate_decisions']['total']} |")
    lines.append(f"| Exact matches | {metrics['duplicate_decisions']['exact_match_count']} |")
    lines.append(f"| Candidate issue references | {metrics['duplicate_decisions']['candidate_issue_count']} |")
    lines.append("")
    lines.extend(markdown_counts("Decision", metrics["duplicate_decisions"]["by_decision"]))
    lines.extend(["## Observability", "", "| Metric | Count |", "|---|---:|"])
    lines.append(f"| Command events | {metrics['observability']['total_events']} |")
    lines.append(f"| Validation retries | {metrics['observability']['validation_retry_count']} |")
    lines.append(f"| Taxonomy normalizations | {metrics['observability']['taxonomy_normalization_count']} |")
    lines.append("")
    lines.extend(markdown_counts("Command events by command", metrics["observability"]["by_command"]))
    lines.extend(markdown_counts("Command events by phase", metrics["observability"]["by_phase"]))
    lines.extend(markdown_counts("Failures by target", metrics["observability"]["failures_by_target"]))
    lines.extend(markdown_counts("Reruns by target", metrics["observability"]["reruns_by_target"]))
    lines.extend(markdown_counts("Validation retries by target", metrics["observability"]["validation_retries_by_target"]))
    lines.extend(markdown_counts("Taxonomy normalizations by target", metrics["observability"]["taxonomy_normalizations_by_target"]))
    lines.extend(["### Execution durations", "", "| Target | Command | Phase | Duration ms | Exit code |", "|---|---|---|---:|---:|"])
    for record in metrics["observability"]["execution_durations"]:
        lines.append(
            f"| {record['target_id']} | {record['command']} | {record['phase']} | "
            f"{record['duration_ms']} | {record['exit_code']} |"
        )
    if not metrics["observability"]["execution_durations"]:
        lines.append("| - | - | - | 0 | 0 |")
    lines.append("")
    lines.extend(["## Artifacts", "", "| Metric | Count |", "|---|---:|"])
    lines.append(f"| Manifest artifacts | {metrics['artifacts']['manifest_artifact_total']} |")
    lines.append(f"| Latest status artifacts | {metrics['artifacts']['latest_status_artifact_count']} |")
    lines.append(f"| Archive artifacts | {metrics['artifacts']['archive_artifact_count']} |")
    lines.append(f"| Manifest hygiene warnings | {metrics['artifacts']['manifest_hygiene_warnings']} |")
    lines.append(f"| Report files | {metrics['artifacts']['reports_file_count']} |")
    lines.append(f"| Report directories | {metrics['artifacts']['reports_dir_count']} |")
    lines.append("")
    lines.extend(markdown_counts("Manifest retention", metrics['artifacts']['manifest_by_retention']))
    lines.append("")
    duration = metrics.get("run_duration", {})
    if duration.get("available"):
        lines.extend(
            [
                "## Run duration",
                "",
                f"- Seconds: `{duration.get('seconds')}`",
                f"- Source: `{duration.get('source')}`",
                "",
            ]
        )
    else:
        lines.extend(["## Run duration", "", "Run duration was not available in local artifacts.", ""])
    return "\n".join(lines)


def write_metrics(
    run_dir: Path,
    out_json: Path | None = None,
    out_md: Path | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    run_dir = run_dir.resolve()
    reports = reports_dir(run_dir)
    metrics = build_metrics(run_dir)
    json_path = out_json.resolve() if out_json else reports / "metrics.json"
    md_path = out_md.resolve() if out_md else reports / "METRICS.md"
    write_json(json_path, metrics)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_metrics_markdown(metrics), encoding="utf-8")
    return json_path, md_path, metrics
