from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from version import auditor_version


MANIFEST_FILENAME = "run-manifest.json"
SCHEMA_FILENAME = "run-manifest.schema.json"
RETENTION_LATEST = "latest"
RETENTION_SUPPORTING = "supporting"
RETENTION_ARCHIVE = "archive"
RETENTION_CATEGORIES = {RETENTION_LATEST, RETENTION_SUPPORTING, RETENTION_ARCHIVE}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_status_paths(run_dir: Path) -> set[str]:
    return {
        "run-summary.txt",
        "report-validation.txt",
        reports_artifact(run_dir, "findings.json"),
        reports_artifact(run_dir, "FINDINGS.md"),
        reports_artifact(run_dir, "targets.json"),
        reports_artifact(run_dir, "COVERAGE.md"),
        reports_artifact(run_dir, "gapfill-targets.json"),
        reports_artifact(run_dir, "metrics.json"),
        reports_artifact(run_dir, "METRICS.md"),
        reports_artifact(run_dir, "benchmark.json"),
        reports_artifact(run_dir, "BENCHMARK.md"),
        reports_artifact(run_dir, "workflow-profile.json"),
        reports_artifact(run_dir, "WORKFLOW_PROFILE.md"),
        reports_artifact(run_dir, "workflow-execution.json"),
        reports_artifact(run_dir, "WORKFLOW_EXECUTION.md"),
        reports_artifact(run_dir, "evidence-graph.json"),
        reports_artifact(run_dir, "EVIDENCE_GRAPH.md"),
        reports_artifact(run_dir, "imported-findings.json"),
        reports_artifact(run_dir, "IMPORTED_FINDINGS.md"),
        reports_artifact(run_dir, "known-findings.json"),
        reports_artifact(run_dir, "NOVELTY.md"),
        reports_artifact(run_dir, "issue-ledger.json"),
        reports_artifact(run_dir, "run-state.json"),
        reports_artifact(run_dir, "dashboard.html"),
    }


def artifact_retention(run_dir: Path, rel_path: str) -> str:
    normalized = Path(rel_path).as_posix()
    reports_root = reports_artifact(run_dir)
    archive_root_files = {
        "prompt.exec.md",
        "prompt.goal.md",
        "codex-events.jsonl",
        "codex-final.md",
        "codex-stderr.txt",
        "codex-transcript.txt",
    }
    if normalized in latest_status_paths(run_dir):
        return RETENTION_LATEST
    if (
        normalized.startswith("prompts/")
        or normalized in archive_root_files
        or normalized.startswith(f"{reports_root}/target-research/")
        or normalized == f"{reports_root}/target-research"
        or normalized.startswith(f"{reports_root}/variant-analysis/")
        or normalized == f"{reports_root}/variant-analysis"
        or normalized.startswith(f"{reports_root}/scanner-results/")
        or normalized == f"{reports_root}/scanner-results"
    ):
        return RETENTION_ARCHIVE
    return RETENTION_SUPPORTING


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def rel_to_run(run_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return str(path)


def artifact_entry(run_dir: Path, rel_path: str, *, kind: str | None = None) -> dict[str, Any] | None:
    path = run_dir / rel_path
    if not path.exists():
        return None
    if kind is None:
        kind = "dir" if path.is_dir() else "file"
    retention = artifact_retention(run_dir, rel_path)
    entry: dict[str, Any] = {"path": rel_path, "kind": kind, "retention": retention}
    if path.is_file():
        entry["size_bytes"] = path.stat().st_size
        entry["sha256"] = file_sha256(path)
    return entry


def reports_artifact(run_dir: Path, rel_path: str = "") -> str:
    ctx = load_json(run_dir / "context.json", {}) or {}
    reports = manifest_relative_path(run_dir, ctx.get("reports_dir"), "reports")
    if not rel_path:
        return reports
    return (Path(reports) / rel_path).as_posix()


def collect_artifacts(run_dir: Path) -> list[dict[str, Any]]:
    candidates = [
        ("context.json", "file"),
        # Omit run-manifest.json from its own artifact list to avoid
        # self-referential size metadata that can never be fully stable.
        ("findings.schema.json", "file"),
        ("targets.schema.json", "file"),
        ("scanner-index.schema.json", "file"),
        ("validation.schema.json", "file"),
        ("chains.schema.json", "file"),
        ("proofs.schema.json", "file"),
        ("traces.schema.json", "file"),
        ("metrics.schema.json", "file"),
        ("benchmark.schema.json", "file"),
        ("workflow-profile.schema.json", "file"),
        ("workflow-execution.schema.json", "file"),
        ("evidence-graph.schema.json", "file"),
        ("imported-findings.schema.json", "file"),
        ("command-event.schema.json", "file"),
        (SCHEMA_FILENAME, "file"),
        ("prompt.exec.md", "file"),
        ("prompt.goal.md", "file"),
        (reports_artifact(run_dir), "dir"),
        (reports_artifact(run_dir, "findings.json"), "file"),
        (reports_artifact(run_dir, "FINDINGS.md"), "file"),
        (reports_artifact(run_dir, "targets.json"), "file"),
        (reports_artifact(run_dir, "COVERAGE.md"), "file"),
        (reports_artifact(run_dir, "gapfill-targets.json"), "file"),
        (reports_artifact(run_dir, "validation.json"), "file"),
        (reports_artifact(run_dir, "VALIDATION.md"), "file"),
        (reports_artifact(run_dir, "chains.json"), "file"),
        (reports_artifact(run_dir, "ATTACK_CHAINS.md"), "file"),
        (reports_artifact(run_dir, "proofs.json"), "file"),
        (reports_artifact(run_dir, "PROOFS.md"), "file"),
        (reports_artifact(run_dir, "proofs"), "dir"),
        (reports_artifact(run_dir, "traces.json"), "file"),
        (reports_artifact(run_dir, "TRACE.md"), "file"),
        (reports_artifact(run_dir, "traces"), "dir"),
        (reports_artifact(run_dir, "metrics.json"), "file"),
        (reports_artifact(run_dir, "METRICS.md"), "file"),
        (reports_artifact(run_dir, "benchmark.json"), "file"),
        (reports_artifact(run_dir, "BENCHMARK.md"), "file"),
        (reports_artifact(run_dir, "workflow-profile.json"), "file"),
        (reports_artifact(run_dir, "WORKFLOW_PROFILE.md"), "file"),
        (reports_artifact(run_dir, "workflow-execution.json"), "file"),
        (reports_artifact(run_dir, "WORKFLOW_EXECUTION.md"), "file"),
        (reports_artifact(run_dir, "evidence-graph.json"), "file"),
        (reports_artifact(run_dir, "EVIDENCE_GRAPH.md"), "file"),
        (reports_artifact(run_dir, "imported-findings.json"), "file"),
        (reports_artifact(run_dir, "IMPORTED_FINDINGS.md"), "file"),
        (reports_artifact(run_dir, "known-findings.json"), "file"),
        (reports_artifact(run_dir, "NOVELTY.md"), "file"),
        (reports_artifact(run_dir, "issue-ledger.json"), "file"),
        (reports_artifact(run_dir, "duplicate-decisions"), "dir"),
        (reports_artifact(run_dir, "run-state.json"), "file"),
        (reports_artifact(run_dir, "command-events.jsonl"), "file"),
        (reports_artifact(run_dir, "scanner-results/scanner-index.json"), "file"),
        (reports_artifact(run_dir, "dashboard.html"), "file"),
        (reports_artifact(run_dir, "findings.sarif"), "file"),
        (reports_artifact(run_dir, "issue-drafts"), "dir"),
        (reports_artifact(run_dir, "scanner-results"), "dir"),
        (reports_artifact(run_dir, "target-research"), "dir"),
        (reports_artifact(run_dir, "variant-analysis"), "dir"),
        ("codex-events.jsonl", "file"),
        ("codex-final.md", "file"),
        ("codex-stderr.txt", "file"),
        ("codex-transcript.txt", "file"),
        ("report-validation.txt", "file"),
        ("run-summary.txt", "file"),
    ]
    entries: list[dict[str, Any]] = []
    for rel_path, kind in candidates:
        entry = artifact_entry(run_dir, rel_path, kind=kind)
        if entry is not None:
            entries.append(entry)

    prompts_dir = run_dir / "prompts"
    if prompts_dir.exists():
        for prompt in sorted(prompts_dir.rglob("*.md")):
            if prompt.is_file():
                rel_path = rel_to_run(run_dir, prompt)
                entries.append({
                    "path": rel_path,
                    "kind": "file",
                    "retention": artifact_retention(run_dir, rel_path),
                    "size_bytes": prompt.stat().st_size,
                    "sha256": file_sha256(prompt),
                })
    return entries


def artifact_retention_summary(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    by_retention: dict[str, int] = {name: 0 for name in sorted(RETENTION_CATEGORIES)}
    latest_paths: list[str] = []
    archive_paths: list[str] = []
    supporting_paths: list[str] = []
    for artifact in artifacts:
        retention = str(artifact.get("retention") or "")
        if retention not in RETENTION_CATEGORIES:
            retention = "unknown"
        by_retention[retention] = by_retention.get(retention, 0) + 1
        path = str(artifact.get("path") or "")
        if retention == RETENTION_LATEST:
            latest_paths.append(path)
        elif retention == RETENTION_ARCHIVE:
            archive_paths.append(path)
        elif retention == RETENTION_SUPPORTING:
            supporting_paths.append(path)
    return {
        "latest_status_artifacts": latest_paths,
        "supporting_artifacts": supporting_paths,
        "archive_artifacts": archive_paths,
        "by_retention": by_retention,
        "notes": "Latest status artifacts are the canonical handoff set. Archive artifacts are retained for reproducibility but excluded from active report validation targets.",
    }


def collect_schemas(run_dir: Path) -> list[dict[str, str]]:
    schemas = []
    for name in [
        "findings.schema.json",
        "targets.schema.json",
        "scanner-index.schema.json",
        "validation.schema.json",
        "chains.schema.json",
        "proofs.schema.json",
        "remediation-candidates.schema.json",
        "patch-validation.schema.json",
        "novelty.schema.json",
        "traces.schema.json",
        "metrics.schema.json",
        "benchmark.schema.json",
        "workflow-profile.schema.json",
        "workflow-execution.schema.json",
        "evidence-graph.schema.json",
        "imported-findings.schema.json",
        "issue-ledger.schema.json",
        "duplicate-decision.schema.json",
        "run-state.schema.json",
        "command-event.schema.json",
        SCHEMA_FILENAME,
    ]:
        path = run_dir / name
        if path.exists():
            schemas.append({"name": name, "path": name})
    return schemas


def none_if_empty(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value


def manifest_relative_path(run_dir: Path, value: Any, default: str) -> str:
    text = str(value or default)
    path = Path(text)
    if path.is_absolute():
        try:
            text = path.relative_to(run_dir).as_posix()
        except ValueError:
            return default
    else:
        text = path.as_posix()
    if text in {"", "."}:
        return default
    if text == ".." or text.startswith("../"):
        return default
    return text


def build_manifest(
    *,
    lab_root: Path,
    run_dir: Path,
    command_name: str,
    mode: str,
    model: str,
    effort: str,
    depth: str,
    network_allowed: bool,
    codex_json: bool,
    allow_invalid_report: bool,
    execution_phase: str,
    codex_status: str | None = None,
    validation_status: str | None = None,
    final_status: str | None = None,
) -> dict[str, Any]:
    context = load_json(run_dir / "context.json", {}) or {}
    artifacts = collect_artifacts(run_dir)
    return {
        "schema_version": "1",
        "generated_at": utc_now(),
        "generated_by": {
            "name": "genai-repo-auditor",
            "version": auditor_version(lab_root),
        },
        "run": {
            "run_id": context.get("run_id") or run_dir.name,
            "repo": context.get("repo", ""),
            "repo_slug": context.get("repo_slug", ""),
            "branch": context.get("branch", ""),
            "commit": context.get("commit", ""),
            "visibility": context.get("visibility", "UNKNOWN"),
        },
        "command": {
            "name": command_name,
            "mode": mode,
            "model": model,
            "effort": effort,
            "clone_depth": depth,
            "network_allowed": network_allowed,
            "codex_json": codex_json,
            "allow_invalid_report": allow_invalid_report,
        },
        "paths": {
            "run_dir": ".",
            "target_repo_dir": manifest_relative_path(run_dir, context.get("target_repo_dir"), "repo"),
            "reports_dir": manifest_relative_path(run_dir, context.get("reports_dir"), "reports"),
        },
        "schemas": collect_schemas(run_dir),
        "artifacts": artifacts,
        "artifact_retention": artifact_retention_summary(artifacts),
        "execution": {
            "phase": execution_phase,
            "codex_status": none_if_empty(codex_status),
            "validation_status": none_if_empty(validation_status),
            "final_status": none_if_empty(final_status),
        },
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write GenAI Repo Auditor run manifest metadata")
    parser.add_argument("--lab-root", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--command-name", default="gra-audit")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    parser.add_argument("--depth", required=True)
    parser.add_argument("--network-allowed", required=True)
    parser.add_argument("--codex-json", required=True)
    parser.add_argument("--allow-invalid-report", required=True)
    parser.add_argument("--execution-phase", required=True)
    parser.add_argument("--codex-status")
    parser.add_argument("--validation-status")
    parser.add_argument("--final-status")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lab_root = Path(args.lab_root).resolve()
    run_dir = Path(args.run_dir).resolve()
    manifest = build_manifest(
        lab_root=lab_root,
        run_dir=run_dir,
        command_name=args.command_name,
        mode=args.mode,
        model=args.model,
        effort=args.effort,
        depth=args.depth,
        network_allowed=parse_bool(args.network_allowed),
        codex_json=parse_bool(args.codex_json),
        allow_invalid_report=parse_bool(args.allow_invalid_report),
        execution_phase=args.execution_phase,
        codex_status=args.codex_status,
        validation_status=args.validation_status,
        final_status=args.final_status,
    )
    write_manifest(run_dir / MANIFEST_FILENAME, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
