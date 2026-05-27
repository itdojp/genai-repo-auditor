from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any

from gralib import load_context, utc_now, write_json

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


class MetricsError(RuntimeError):
    pass


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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
    generated_from_artifact = 0
    if isinstance(gapfill_data, dict):
        generated = gapfill_data.get("generated_targets")
        if isinstance(generated, list):
            generated_from_artifact = len([item for item in generated if isinstance(item, dict)])
        elif isinstance(gapfill_data.get("generated_target_count"), int):
            generated_from_artifact = int(gapfill_data["generated_target_count"])
    return {
        "coverage_artifact_present": coverage_present,
        "gapfill_artifact_present": gapfill_present,
        "source_targets_recommended": recommended,
        "targets_generated": max(len(gapfill_targets), generated_from_artifact),
        "targets_reviewed": sum(1 for t in gapfill_targets if t.get("status") == "reviewed"),
        "targets_by_status": count_known(gapfill_targets, "status", TARGET_STATUSES, "unknown"),
    }


def trace_metrics(traces: list[dict[str, Any]], present: bool) -> dict[str, Any]:
    return {
        "artifact_present": present,
        "total": len(traces),
        "by_reachable": count_known(traces, "reachable", TRACE_VALUES, "Not assessed"),
        "by_attacker_control": count_known(traces, "attacker_control", TRACE_VALUES, "Not assessed"),
        "by_status": count_known(traces, "status", COUNT_STATUSES, "Unknown"),
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
    manifest = load_json(run_dir / "run-manifest.json", None)

    findings = list_of_dicts(findings_data, "findings")
    targets = list_of_dicts(targets_data, "targets")
    validations = list_of_dicts(validation_data, "validations")
    chains = list_of_dicts(chains_data, "chains")
    proofs = list_of_dicts(proofs_data, "proofs")
    traces = list_of_dicts(traces_data, "traces")

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
        "findings": finding_metrics(findings),
        "adversarial_validation": validation_metrics(validations, validation_data is not None),
        "chains": chain_metrics(chains, chains_data is not None),
        "proofs": proof_metrics(proofs, proofs_data is not None),
        "gapfill": gapfill_metrics(
            targets,
            gapfill_data,
            (reports / "COVERAGE.md").exists(),
            gapfill_data is not None,
        ),
        "traces": trace_metrics(traces, traces_data is not None),
        "issue_publication_plan": issue_plan_metrics(issue_plan, issue_plan is not None),
        "artifacts": artifact_metrics(run_dir, reports, manifest),
        "run_duration": run_duration_metrics(manifest),
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
        f"| Gapfill targets generated | {metrics['gapfill']['targets_generated']} |",
        f"| Traces | {metrics['traces']['total']} |",
        f"| Issue plan warnings | {metrics['issue_publication_plan']['warning_count']} |",
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
    lines.append(f"| Targets generated | {metrics['gapfill']['targets_generated']} |")
    lines.append(f"| Targets reviewed | {metrics['gapfill']['targets_reviewed']} |")
    lines.append("")
    lines.extend(["## Traces", ""])
    lines.extend(markdown_counts("Trace reachable", metrics["traces"]["by_reachable"]))
    lines.extend(markdown_counts("Trace attacker control", metrics["traces"]["by_attacker_control"]))
    lines.extend(markdown_counts("Trace status", metrics["traces"]["by_status"]))
    lines.extend(["## Issue publication plan", "", "| Metric | Count |", "|---|---:|"])
    lines.append(f"| Selected findings | {metrics['issue_publication_plan']['selected_findings']} |")
    lines.append(f"| Warnings | {metrics['issue_publication_plan']['warning_count']} |")
    lines.append("")
    lines.extend(["## Artifacts", "", "| Metric | Count |", "|---|---:|"])
    lines.append(f"| Manifest artifacts | {metrics['artifacts']['manifest_artifact_total']} |")
    lines.append(f"| Report files | {metrics['artifacts']['reports_file_count']} |")
    lines.append(f"| Report directories | {metrics['artifacts']['reports_dir_count']} |")
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
