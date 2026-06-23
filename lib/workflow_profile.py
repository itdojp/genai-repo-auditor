from __future__ import annotations

from collections import Counter
from pathlib import Path, PureWindowsPath
from typing import Any

from gralib import load_context, load_json, utc_now, write_json
from report_safety import iter_secret_findings


PROFILE_RECON_ONLY = "recon-only"
PROFILES = {PROFILE_RECON_ONLY}

STAGE_STATUSES = [
    "completed",
    "skipped_by_scope",
    "not_started",
    "failed",
    "not_applicable",
]

RECON_ONLY_STAGES = [
    {
        "id": "prepare",
        "title": "Prepare isolated audit run",
        "status": "completed",
        "reason": "The run directory and context were prepared before recording the recon-only profile.",
        "expected_artifacts": ["context.json", "run-manifest.json"],
        "publication_blocking": False,
    },
    {
        "id": "reconnaissance",
        "title": "Repository reconnaissance",
        "status": "completed",
        "reason": "Reconnaissance is the highest required review depth for this profile.",
        "expected_artifacts": [
            "reports/AUDIT_SUMMARY.md",
            "reports/THREAT_MODEL.md",
            "reports/ATTACK_SURFACE.md",
        ],
        "publication_blocking": False,
    },
    {
        "id": "target_generation",
        "title": "Target queue generation",
        "status": "completed",
        "reason": "Target generation may be used to document future scope without starting deep research.",
        "expected_artifacts": ["reports/targets.json"],
        "publication_blocking": False,
    },
    {
        "id": "target_research",
        "title": "Deep target research",
        "status": "skipped_by_scope",
        "reason": "Recon-only profile intentionally stops before per-target deep review.",
        "expected_artifacts": [],
        "publication_blocking": False,
    },
    {
        "id": "scanner_ingestion",
        "title": "Scanner artifact ingestion",
        "status": "skipped_by_scope",
        "reason": "No current-run authorized scanner artifact is required for a recon-only scope.",
        "expected_artifacts": [],
        "publication_blocking": False,
    },
    {
        "id": "scanner_triage",
        "title": "Scanner lead triage",
        "status": "skipped_by_scope",
        "reason": "Scanner leads are not triaged when scanner ingestion is out of scope.",
        "expected_artifacts": [],
        "publication_blocking": False,
    },
    {
        "id": "adversarial_validation",
        "title": "Adversarial validation",
        "status": "skipped_by_scope",
        "reason": "No confirmed or probable finding is being advanced into adversarial validation.",
        "expected_artifacts": [],
        "publication_blocking": False,
    },
    {
        "id": "chain_synthesis",
        "title": "Defensive chain synthesis",
        "status": "skipped_by_scope",
        "reason": "Attack-chain synthesis is intentionally deferred until findings or target evidence warrant it.",
        "expected_artifacts": [],
        "publication_blocking": False,
    },
    {
        "id": "safe_proofs",
        "title": "Safe local proofs",
        "status": "skipped_by_scope",
        "reason": "Proof generation is intentionally deferred because recon-only runs do not validate exploitability.",
        "expected_artifacts": [],
        "publication_blocking": False,
    },
    {
        "id": "trace_reachability",
        "title": "Cross-repo trace reachability",
        "status": "skipped_by_scope",
        "reason": "Trace reachability is intentionally deferred until a finding requires cross-repository validation.",
        "expected_artifacts": [],
        "publication_blocking": False,
    },
    {
        "id": "remediation",
        "title": "Draft remediation candidates",
        "status": "skipped_by_scope",
        "reason": "No remediation candidate is generated without an approved finding or scoped follow-up.",
        "expected_artifacts": [],
        "publication_blocking": False,
    },
    {
        "id": "dashboard",
        "title": "Dashboard generation",
        "status": "skipped_by_scope",
        "reason": "Dashboard generation is optional and may be skipped when local Markdown/JSON summaries are sufficient.",
        "expected_artifacts": [],
        "publication_blocking": False,
    },
    {
        "id": "issue_publication",
        "title": "GitHub Issue publication",
        "status": "skipped_by_scope",
        "reason": "Recon-only runs do not publish issues unless later human review creates a separate finding workflow.",
        "expected_artifacts": [],
        "publication_blocking": False,
    },
]


class WorkflowProfileError(RuntimeError):
    pass


def _non_empty_text(value: str, label: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise WorkflowProfileError(f"{label} must not be empty")
    return text


def reports_dir(run_dir: Path, ctx: dict[str, Any]) -> Path:
    raw = Path(str(ctx.get("reports_dir", "reports") or "reports"))
    if raw.is_absolute() or PureWindowsPath(str(raw)).is_absolute():
        raise WorkflowProfileError(f"reports_dir must be relative under the run directory: {raw}")
    if raw == Path(".") or ".." in raw.parts:
        raise WorkflowProfileError(f"reports_dir must be relative under the run directory: {raw}")
    current = run_dir
    for part in raw.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise WorkflowProfileError(f"reports_dir must not contain symlink components: {raw}")
    reports = run_dir / raw
    try:
        reports.resolve(strict=False).relative_to(run_dir.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise WorkflowProfileError(f"reports_dir must stay under the run directory: {raw}") from exc
    return reports


def stage_status_counts(stages: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(stage.get("status") or "not_started") for stage in stages if isinstance(stage, dict))
    result = {status: int(counts.get(status, 0)) for status in STAGE_STATUSES}
    for status, count in sorted(counts.items()):
        if status not in result:
            result[status] = int(count)
    return result


def summarize_stages(stages: list[dict[str, Any]]) -> dict[str, Any]:
    scoped = [str(stage.get("id") or "") for stage in stages if stage.get("status") == "skipped_by_scope"]
    failed = [str(stage.get("id") or "") for stage in stages if stage.get("status") == "failed"]
    return {
        "stage_count": len(stages),
        "by_status": stage_status_counts(stages),
        "skipped_by_scope_count": len(scoped),
        "scoped_skip_stages": scoped,
        "failed_count": len(failed),
        "failed_stages": failed,
    }


def build_workflow_profile(
    run_dir: Path,
    *,
    profile: str,
    rationale: str,
    reviewer: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    ctx = load_context(run_dir)
    if profile not in PROFILES:
        allowed = ", ".join(sorted(PROFILES))
        raise WorkflowProfileError(f"profile must be one of: {allowed}")
    rationale_text = _non_empty_text(rationale, "rationale")
    reviewer_text = " ".join(str(reviewer or "").split())
    stages = [dict(stage) for stage in RECON_ONLY_STAGES]
    summary = summarize_stages(stages)
    generated = generated_at or utc_now()
    return {
        "schema_version": "1",
        "run_id": str(ctx.get("run_id") or run_dir.name),
        "repo": str(ctx.get("repo") or ""),
        "branch": str(ctx.get("branch") or ""),
        "commit": str(ctx.get("commit") or ""),
        "generated_at": generated,
        "source": "gra-workflow-profile",
        "profile": profile,
        "rationale": rationale_text,
        "reviewer": reviewer_text,
        "safety": {
            "local_artifacts_only": True,
            "raw_evidence_copied": False,
            "secrets_copied": False,
            "issue_bodies_created": False,
            "bounded_summaries_only": True,
        },
        "summary": summary,
        "stages": stages,
    }


def summarize_workflow_profile(profile_data: Any) -> dict[str, Any]:
    if not isinstance(profile_data, dict):
        return {
            "artifact_present": False,
            "profile": "not-recorded",
            "stage_count": 0,
            "by_status": {status: 0 for status in STAGE_STATUSES},
            "skipped_by_scope_count": 0,
            "scoped_skip_stages": [],
            "failed_count": 0,
            "failed_stages": [],
        }
    stages = [stage for stage in profile_data.get("stages") or [] if isinstance(stage, dict)]
    summary = summarize_stages(stages)
    return {
        "artifact_present": True,
        "profile": str(profile_data.get("profile") or "unknown"),
        **summary,
    }


def validate_workflow_profile_payload(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["workflow_profile: expected object"]
    if value.get("source") != "gra-workflow-profile":
        errors.append("workflow_profile.source: must be gra-workflow-profile")
    if value.get("profile") not in PROFILES:
        errors.append(f"workflow_profile.profile: must be one of {sorted(PROFILES)}")
    if not isinstance(value.get("rationale"), str) or not str(value.get("rationale") or "").strip():
        errors.append("workflow_profile.rationale: must be a non-empty string")
    safety = value.get("safety") if isinstance(value.get("safety"), dict) else {}
    expected_safety = {
        "local_artifacts_only": True,
        "raw_evidence_copied": False,
        "secrets_copied": False,
        "issue_bodies_created": False,
        "bounded_summaries_only": True,
    }
    for key, expected in expected_safety.items():
        if safety.get(key) is not expected:
            errors.append(f"workflow_profile.safety.{key}: must be {str(expected).lower()}")
    stages = value.get("stages")
    if not isinstance(stages, list):
        errors.append("workflow_profile.stages: must be a list")
        stages = []
    stage_ids: set[str] = set()
    valid_stage_records: list[dict[str, Any]] = []
    for index, stage in enumerate(stages):
        path = f"workflow_profile.stages[{index}]"
        if not isinstance(stage, dict):
            errors.append(f"{path}: stage must be an object")
            continue
        valid_stage_records.append(stage)
        stage_id = str(stage.get("id") or "")
        if not stage_id:
            errors.append(f"{path}.id: must not be empty")
        elif stage_id in stage_ids:
            errors.append(f"{path}.id: duplicate stage id {stage_id}")
        stage_ids.add(stage_id)
        if stage.get("status") not in STAGE_STATUSES:
            errors.append(f"{path}.status: invalid status {stage.get('status')!r}")
        for key in ["title", "reason"]:
            if not isinstance(stage.get(key), str) or not str(stage.get(key) or "").strip():
                errors.append(f"{path}.{key}: must be a non-empty string")
        expected = stage.get("expected_artifacts")
        if not isinstance(expected, list):
            errors.append(f"{path}.expected_artifacts: must be a list")
        else:
            for artifact_index, artifact in enumerate(expected):
                if not isinstance(artifact, str):
                    errors.append(f"{path}.expected_artifacts[{artifact_index}]: expected type string")
        if not isinstance(stage.get("publication_blocking"), bool):
            errors.append(f"{path}.publication_blocking: must be boolean")

    expected_summary = summarize_stages(valid_stage_records)
    summary = value.get("summary") if isinstance(value.get("summary"), dict) else {}
    for key in ["stage_count", "skipped_by_scope_count", "failed_count"]:
        if summary.get(key) != expected_summary[key]:
            errors.append(f"workflow_profile.summary.{key}: value does not match stages")
    if summary.get("by_status") != expected_summary["by_status"]:
        errors.append("workflow_profile.summary.by_status: value does not match stages")
    if summary.get("scoped_skip_stages") != expected_summary["scoped_skip_stages"]:
        errors.append("workflow_profile.summary.scoped_skip_stages: value does not match stages")
    if summary.get("failed_stages") != expected_summary["failed_stages"]:
        errors.append("workflow_profile.summary.failed_stages: value does not match stages")
    for finding in iter_secret_findings(value, field_path="workflow_profile"):
        errors.append(finding)
    return errors


def write_workflow_profile(
    run_dir: Path,
    *,
    profile: str,
    rationale: str,
    reviewer: str | None = None,
    force: bool = False,
) -> tuple[Path, Path, dict[str, Any]]:
    run_dir = run_dir.resolve()
    if not (run_dir / "context.json").is_file():
        raise WorkflowProfileError(f"context.json not found under {run_dir}")
    ctx = load_context(run_dir)
    reports = reports_dir(run_dir, ctx)
    profile_path = reports / "workflow-profile.json"
    if profile_path.exists() and not force:
        raise WorkflowProfileError("workflow-profile.json already exists; use --force only after reviewing the existing scope record")
    profile_data = build_workflow_profile(
        run_dir,
        profile=profile,
        rationale=rationale,
        reviewer=reviewer,
    )
    payload_errors = validate_workflow_profile_payload(profile_data)
    if payload_errors:
        raise WorkflowProfileError("workflow profile failed internal validation: " + "; ".join(payload_errors[:5]))
    write_json(profile_path, profile_data)
    md_path = reports / "WORKFLOW_PROFILE.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_workflow_profile_markdown(profile_data), encoding="utf-8")
    return profile_path, md_path, profile_data


def render_workflow_profile_markdown(profile_data: dict[str, Any]) -> str:
    summary = profile_data.get("summary") if isinstance(profile_data.get("summary"), dict) else {}
    lines = [
        "# Workflow Profile",
        "",
        "Local-only workflow scope record for a GenAI Repo Auditor run.",
        "This report records stage intent and aggregate status only; it excludes raw evidence, finding bodies, issue bodies, proof payloads, scanner lead bodies, remediation content, and secret values.",
        "",
        "## Scope",
        "",
        f"- Profile: `{profile_data.get('profile', '')}`",
        f"- Run ID: `{profile_data.get('run_id', '')}`",
        f"- Repository: `{profile_data.get('repo', '')}`",
        f"- Commit: `{profile_data.get('commit', '')}`",
        f"- Generated at: `{profile_data.get('generated_at', '')}`",
        f"- Reviewer: `{profile_data.get('reviewer') or 'not recorded'}`",
        "",
        "## Rationale",
        "",
        str(profile_data.get("rationale") or ""),
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Stage count | {summary.get('stage_count', 0)} |",
        f"| Skipped by scope | {summary.get('skipped_by_scope_count', 0)} |",
        f"| Failed stages | {summary.get('failed_count', 0)} |",
        "",
        "## Stages",
        "",
        "| Stage | Status | Reason |",
        "|---|---|---|",
    ]
    for stage in profile_data.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        lines.append(
            f"| `{stage.get('id', '')}` | `{stage.get('status', '')}` | {stage.get('reason', '')} |"
        )
    lines.extend(
        [
            "",
            "## Safety notes",
            "",
            "- `skipped_by_scope` means intentionally out of scope for this run, not missing output and not command failure.",
            "- Use deterministic reporting commands after writing this profile so downstream summaries can surface scoped skips.",
            "",
        ]
    )
    return "\n".join(lines)


def load_workflow_profile(reports: Path) -> Any:
    return load_json(reports / "workflow-profile.json", None)
