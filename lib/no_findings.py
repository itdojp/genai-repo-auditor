from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from gralib import load_context, utc_now, write_json, load_json

SOURCE_STAGES = {
    "recon",
    "target-queue",
    "scanner-triage",
    "manual-review",
    "validation",
    "other",
}


class NoFindingsError(RuntimeError):
    pass


def _non_empty_text(value: str, label: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise NoFindingsError(f"{label} must not be empty")
    return text


def _git_commit(repo_dir: Path) -> str:
    if not repo_dir.is_dir():
        return ""
    try:
        cp = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if cp.returncode != 0:
        return ""
    return cp.stdout.strip()


def reports_dir(run_dir: Path, ctx: dict[str, Any]) -> Path:
    raw = Path(str(ctx.get("reports_dir", "reports") or "reports"))
    if raw.is_absolute() or ".." in raw.parts:
        raise NoFindingsError(f"reports_dir must be relative under the run directory: {raw}")
    return run_dir / raw


def target_repo_dir(run_dir: Path, ctx: dict[str, Any]) -> Path:
    raw = Path(str(ctx.get("target_repo_dir", "repo") or "repo"))
    if raw.is_absolute() or ".." in raw.parts:
        raise NoFindingsError(f"target_repo_dir must be relative under the run directory: {raw}")
    return run_dir / raw


def build_no_findings_report(
    run_dir: Path,
    *,
    rationale: str,
    source_stage: str,
    reviewer: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    ctx = load_context(run_dir)
    if source_stage not in SOURCE_STAGES:
        allowed = ", ".join(sorted(SOURCE_STAGES))
        raise NoFindingsError(f"source_stage must be one of: {allowed}")
    rationale_text = _non_empty_text(rationale, "rationale")
    reviewer_text = " ".join(str(reviewer or "").split())
    repo_dir = target_repo_dir(run_dir, ctx)
    commit = str(ctx.get("commit") or "").strip() or _git_commit(repo_dir)
    generated = generated_at or utc_now()
    return {
        "run_id": str(ctx.get("run_id") or run_dir.name),
        "repo": str(ctx.get("repo") or ""),
        "branch": ctx.get("branch", ""),
        "commit": commit,
        "visibility": str(ctx.get("visibility") or "UNKNOWN"),
        "generated_at": generated,
        "findings": [],
        "no_findings": {
            "schema_version": "1",
            "status": "no-confirmed-findings",
            "rationale": rationale_text,
            "source_stage": source_stage,
            "recorded_at": generated,
            "recorded_by": "gra-no-findings",
            "reviewer": reviewer_text,
            "target_metadata": {
                "run_id": str(ctx.get("run_id") or run_dir.name),
                "repo": str(ctx.get("repo") or ""),
                "branch": ctx.get("branch", ""),
                "commit": commit,
                "visibility": str(ctx.get("visibility") or "UNKNOWN"),
            },
            "safety": {
                "no_finding_bodies": True,
                "issue_bodies_created": False,
                "raw_evidence_copied": False,
                "safe_for_public_summary_after_review": True,
            },
        },
    }


def existing_findings_count(path: Path) -> int | None:
    if not path.exists():
        return None
    data = load_json(path, {}) or {}
    if not isinstance(data, dict):
        raise NoFindingsError("existing findings.json must be a JSON object")
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise NoFindingsError("existing findings.json must contain findings array")
    return len([item for item in findings if isinstance(item, dict)])


def write_no_findings_report(
    run_dir: Path,
    *,
    rationale: str,
    source_stage: str,
    reviewer: str | None = None,
    force: bool = False,
) -> tuple[Path, Path, dict[str, Any]]:
    run_dir = run_dir.resolve()
    if not (run_dir / "context.json").is_file():
        raise NoFindingsError(f"context.json not found under {run_dir}")
    ctx = load_context(run_dir)
    reports = reports_dir(run_dir, ctx)
    findings_path = reports / "findings.json"
    existing_count = existing_findings_count(findings_path)
    if existing_count is not None and not force:
        raise NoFindingsError(f"findings.json already exists with {existing_count} finding(s); use --force only after review")
    report = build_no_findings_report(
        run_dir,
        rationale=rationale,
        source_stage=source_stage,
        reviewer=reviewer,
    )
    write_json(findings_path, report)
    md_path = reports / "NO_FINDINGS.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    nf = report["no_findings"]
    metadata = nf["target_metadata"]
    md_path.write_text(
        "\n".join(
            [
                "# No Confirmed Findings Record",
                "",
                "This local report records an explicit no-confirmed-finding state for a bounded GenAI Repo Auditor run.",
                "It contains no finding bodies, issue bodies, raw evidence, scanner output, proof payloads, traces, or remediation content.",
                "",
                "## Target metadata",
                "",
                "| Field | Value |",
                "|---|---|",
                f"| Run ID | `{metadata['run_id']}` |",
                f"| Repository | `{metadata['repo']}` |",
                f"| Branch | `{metadata['branch']}` |",
                f"| Commit | `{metadata['commit']}` |",
                f"| Visibility | `{metadata['visibility']}` |",
                "",
                "## Decision",
                "",
                f"- Status: `{nf['status']}`",
                f"- Source stage: `{nf['source_stage']}`",
                f"- Recorded at: `{nf['recorded_at']}`",
                f"- Recorded by: `{nf['recorded_by']}`",
                f"- Reviewer: `{nf['reviewer']}`" if nf.get("reviewer") else "- Reviewer: not recorded",
                "",
                "## Rationale",
                "",
                nf["rationale"],
                "",
                "## Next checks",
                "",
                "Run the deterministic reporting path against the same run directory:",
                "",
                "```bash",
                "gra-validate-report --run RUN_DIR",
                "gra-metrics --run RUN_DIR",
                "gra-benchmark --run RUN_DIR",
                "gra-evidence-graph --run RUN_DIR",
                "gra-issues --run RUN_DIR --dry-run --min-severity Low --statuses Confirmed,Probable,Potential,Informational",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return findings_path, md_path, report
